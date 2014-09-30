import os
import sys
import glob
import numpy
from collections import namedtuple, Iterable
import seiscomp3.Math
import seiscomp3.Core
import waveproc
from math import log10, pi, sqrt
import seiscomp3.Logging
import seiscomp3.Seismology

sys.path.append('/home/javier/seispy/lib/python2.7/site-packages/')

from seis._numeric import bmagn as _bmagn


class Peak(namedtuple('Peak', ['time', 'value'])):
    __slots__ = ()

    def __abs__(self):
        return abs(self.value)

    def __gt__(self, other):
        aux = other
        if isinstance(other, Peak):
            aux = other.value
        return(self.value > aux)

    def __lt__(self, other):
        aux = other
        if isinstance(other, Peak):
            aux = other.value
        return(self.value < aux)

    def before(self, other):
        if isinstance(other, Peak):
            return self.time < other.time
        else:
            return self.time < other

    def after(self, other):
        if isinstance(other, Peak):
            return self.time > other.time
        else:
            return self.time > other


def mysign(number):
    if number == 0:
        return 0

    if number < 0:
        return -1
    return 1


def Q_PV(dist, depth):
    if not 5 <= dist <= 108 or not 0. <= depth <= 800:
        return None
    amp = 1.0
    per = 1.0
    # incl. conversion from nanometers to micrometers
    return _bmagn(0.001 * amp, per, dist, depth)


class Processor(waveproc.Processor):

    def __init__(self, dumpWaveforms=False):
        waveproc.Processor.__init__(self, dumpWaveforms)
        self.name = "mBc"

        # Extra margin for the time windows
        self.margin_begin = 30

        # Filter to apply to the signal
        self.filters = dict()
        # List of peaks recognized in the raw signal
        self.results = dict()
        # List of peaks recognized in the filtered signal
        self.results2 = dict()
        # Magnitude per stream
        self.magnitude = dict()
        # Duration per stream
        self.duration = dict()
        # Effective duration to be applied to all the streams.
        # It is calculated based on the "duration"s of the streams
        self.meanDuration = 0.0

        # Keeps state variables for every stream to recognize maximum values
        # Global maximum per stream
        self.Vmaxt = dict()
        # Current local maximum per stream
        self.Vlocal = dict()
        # Current sign of the signal
        self.signV = dict()
        # This can be shared for the two signals (broad band and high
        # frequency) because the indexes are the same for both of them.
        # Current offset per stream to know the position of every component of
        # the record being currently analyzed
        self.idx = dict()

        # Calculate RMS of the (HF) filtered signal to detect P arrival
        self.rms = dict()
        # P arrival per stream
        self.pReal = dict()

        # "stage" specifies if we are:
        # 1) searching for a maximum
        # 2) checking the quiet period of 30 seconds
        # 3) magnitude was already calculated
        self.stage = dict()

        # Position of the last peak detected
        # FIXME I think it is not needed anymore
        self.posLastPeak = dict()

        # Short notation for the Time Travel Calculation function
        self.ttt = seiscomp3.Seismology.TravelTimeTable()

    def timeWindows(self):
        """Calculate the timewindows based on the event and
        the available inventory"""

        # I include this maximum velocity for the surface waves
        # because it is stated that "the summation time window must end
        # before the arrival of the S wave".
        vmax = 5.0

        self.timeWinDict = dict()

        t0 = self.event.timeSC3

        for key in self.filtered:
            try:
                net, sta, loc, cha = key
            except:
                continue

            # distance calculation
            s = self.filtered[net, sta]
            # This could be moved to every magnitude module
            try:
                ttlist = self.ttt.compute(self.event.lat,
                                          self.event.lon,
                                          self.event.dep,
                                          s.latitude(),
                                          s.longitude(),
                                          s.elevation())
            except Exception, e:
                msg = "Exception from ttt.compute(): " + str(e)
                seiscomp3.Logging.error(msg)
                continue

            # distance calculation
            s = self.filtered[net, sta]
            delta, az, baz = seiscomp3.Math.delazi(self.event.lat,
                                                   self.event.lon,
                                                   s.latitude(),
                                                   s.longitude())
            # Convert from deg to km
            dist_km = delta * 111.195

            # Check all the entries in the table
            for tt in ttlist:
                # until I find the P phase (or similar)
                if tt.phase == 'P' or tt.phase == 'Pdiff':
                    # Limits for the timewindow
                    # P arrival minus a small buffer AND another number of
                    # seconds to calculate the average value of the signal
                    t_from = t0 + seiscomp3.Core.TimeSpan(tt.time -
                                                          self.margin_begin -
                                                          self.peepAvg)
                    # S arrival
                    t_to = t0 + seiscomp3.Core.TimeSpan(dist_km / vmax)
                    break
            else:
                # Something went wrong and I cannot find a P phase arrival
                # time for the parameters given. Try with the next one.
                continue

            # Collect all the necessary timewindows
            self.timeWinDict[net, sta, loc, cha] = (t_from, t_to)

        return

    def _filterInventory(self, inventory):
        # Definitions to filter the available inventory
        # by distance
        deltaMin = 5
        deltaMax = 100
        # and channel type
        # We want to find the BB channel, which is normally BH
        # but sometimes HH, SH etc., so we try each of these
        channels = ["BH", "HH", "SH", "MH", "EH", "CH"]

        failed = []

        for key in inventory:

            try:
                # only consider items at the location level
                net, sta, loc = key
            except:
                continue

            # distance filter
            s = inventory[net, sta]
            delta, az, baz = seiscomp3.Math.delazi(self.event.lat,
                                                   self.event.lon,
                                                   s.latitude(),
                                                   s.longitude())
            if delta > deltaMax:
                continue

            if delta < deltaMin:
                continue

            for ch in channels:
                if(((net, sta, loc, ch + "Z") not in inventory) and
                   ((net, sta, loc, ch + "3") not in inventory)):
                    continue

                for c in "Z3":
                    cha = ch + c
                    if (net, sta, loc, cha) in inventory:
                        self.filtered[net, sta, loc, cha] = inventory[
                            net, sta, loc, cha]
                self.filtered[net, sta, loc] = inventory[net, sta, loc]
                self.filtered[net, sta] = inventory[net, sta]
                self.filtered[net] = inventory[net]
                break

            if (net, sta, loc) not in self.filtered:
                failed.append((net, sta, loc))

        for net, sta, loc in failed:
            if (net, sta) not in self.filtered:
                seiscomp3.Logging.warning("could not find suitable stream " +
                                          "for %s.%s.%s" % (net, sta, loc))

        return

    def __checkMax(self, value, Vlocal, Vmaxt, signV, signalID, pos, idx, sps,
                   lowThresh=0.0):
        """Check whether a value is a maximum taking into account the
        previous history of the search.

        value: is the value to check
        Vlocal: tuple with (position, value)
        Vmaxt: tuple with (position, value)
        signV: sign of the current period
        signalID: component of the vectors (Vlocal, Vmaxt, signV) related to
                  this signal.
        pos: position in the current record
        idx: offset of the position of the components of the current record
        sps: samples per second
        lowThresh: minimum value to be considered a maximum

        Returns:
            None if there is no maximum
            A tuple containing (position, value) of the maximum.
                Ready to be added to self.results."""

        q = 0.6

        returnValue = None

        # Check if there is a change in sign (-1, 0, 1)
        if mysign(value) != signV[signalID]:
            # Save the maximum
            if (Vlocal[signalID] is not None) and \
               (abs(Vlocal[signalID]) > lowThresh):
                # By definition, a sample is recognized as a new peak only
                # if its value is greater than the maximum in absolute
                # value multiplied by q (0.6 in Bormann and Saul, 2008)
                # If this is a global maximum

                # Case of a global maximum
                if abs(Vmaxt[signalID]) < abs(Vlocal[signalID]):
                    Vmaxt[signalID] = Vlocal[signalID]
                    returnValue = Vlocal[signalID]

                # Case of a local maximum
                elif (abs(Vlocal[signalID]) >= q * abs(Vmaxt[signalID])):
                    returnValue = Vlocal[signalID]

            # Reset values for the new segment
            Vlocal[signalID] = None

            # Update the sign for the new segment
            signV[signalID] = mysign(value)

        # In case this is the biggest local peak we save it
        if Vlocal[signalID] is None:
            Vlocal[signalID] = Peak((pos + idx) / sps, value)

        elif abs(value) > abs(Vlocal[signalID]):
            Vlocal[signalID] = Peak((pos + idx) / sps, value)

        return returnValue

    def feed(self, rec):
        """Receives a record and update the status of the magnitude calculation
        for the selected stream."""

        # Basic checks are done by the parent class
        if not waveproc.Processor.feed(self, rec):
            return False

        streamID = rec.streamID()

        # If the magnitude was already calculated, get out
        if streamID in self.stage and self.stage[streamID] > 2:
            return False

        #sys.stdout.write('.')
        #sys.stdout.flush()
        #sleep(0.3)

        auxData = rec.data()
        if auxData is None:
            print streamID
            print 'Estamos en problemas'
            return False

        data = auxData.numpy()
        nsamp = len(data)

        n, s, l, c = streamID.split('.')
        gain = self.getGain(n, s, l, c)

        if streamID not in self.rms:
            # Delete an old file in case that this is the first record
            try:
                os.remove("%s-%s%s%s%s.dat" % (self.name, n, s, l, c))
            except OSError:
                pass

            # Idem in the case of filtered data
            try:
                os.remove("%s-%s%s%s%s-f.dat" % (self.name, n, s, l, c))
            except OSError:
                pass

            # Butterworth filter for the Control signal
            # Filter around 2 Hz (1-3)
            self.filters[streamID] = seiscomp3.Math.InPlaceFilterD.Create(
                "BW(4, 1, 3)")
            self.filters[streamID].setSamplingFrequency(self.sps[streamID])

            # Store the RMS of the filtered signal
            self.rms[streamID] = (0, 0)
            # The real P arrival should be detected from (HF) filtered data
            self.pReal[streamID] = None

            # We are looking for a maximum
            self.stage[streamID] = 1

            # List of maximum values
            self.results[streamID] = []
            self.results2[streamID] = []
            self.Vmaxt[streamID] = [Peak(0, 0), Peak(0, 0)]
            self.Vlocal[streamID] = [None, None]
            self.signV[streamID] = [0, 0]
            if streamID not in self.idx:
                self.idx[streamID] = 0
            self.posLastPeak[streamID] = 0

        # Define a SC3 array to copy the data to
        data2 = seiscomp3.Core.DoubleArrayT()
        data2.resize(nsamp)
        # data2.setNumpy(data)

        # To make notation shorter
        dur = self.duration
        res = self.results[streamID]
        res2 = self.results2[streamID]

        # Auxiliary variable to be written in a file
        auxValues = []

        for pos, i in enumerate(data):
            # The signal is scaled with the gain and centered around 0 by
            # substracting the average of the first "peepAvg" seconds
            avg = self.avgValue[streamID] if not isinstance(
                self.avgValue[streamID], tuple) else 0
            data[pos] = i / gain - avg

            relTime = (pos + self.idx[streamID]) / self.sps[streamID]
            # If we should write the output
            if (relTime > self.peepAvg):
                auxValues.append((relTime, data[pos]))

            # Save it to a SC3 array
            # The average is included to avoid a "jump" when we finish with the
            # calculation of the average and the signal is "re-centered"
            # In any case the filter will remove the average
            data2.set(pos, numpy.double(data[pos] + avg))

        # Save waveform to a file
        self.__save2File("%s-%s%s%s%s.dat" % (self.name, n, s, l, c),
                         auxValues, 'a')

        # and apply the filter (1-3 Hz)
        self.filters[streamID].apply(data2)

        pArrival = self.timeWinDict[n, s, l, c][0] + \
            seiscomp3.Core.TimeSpan(self.margin_begin +
                                    self.peepAvg)

        # Auxiliary variable to be written in a file
        auxValues = []

        # Search for local maximum values
        for pos in xrange(nsamp):
            relTime = (pos + self.idx[streamID]) / self.sps[streamID]

            # I cannot process the first "peepAvg" seconds, because I used them
            # to calculate the average
            if relTime < self.peepAvg:
                # WARNING! we are not considering the first 2 seconds of
                # filtered data because could have high values that could
                # artificially affect the RMS
                cumul = (self.rms[streamID][0] + data2.get(pos) *
                         data2.get(pos)) if relTime > 2.0 else 0.0
                count = (self.rms[streamID][1] + 1) if relTime > 2.0 else 0

                self.rms[streamID] = (cumul, count)
                continue
            else:
                if isinstance(self.rms[streamID], tuple):
                    # Finish the calculation fo the RMS
                    if self.rms[streamID][1]:
                        self.rms[streamID] = sqrt(self.rms[streamID][0] /
                                                  self.rms[streamID][1])
                    else:
                        self.rms[streamID] = 0.0

            i = data[pos]

            isMax = self.__checkMax(i, self.Vlocal[streamID],
                                    self.Vmaxt[streamID],
                                    self.signV[streamID], 0,
                                    pos, self.idx[streamID],
                                    self.sps[streamID])

            i2 = data2.get(pos)
            # Only check for a peak in the filtered signal if the theoretical P
            # arrival is already there
            if self.startTime[streamID] + relTime < pArrival.length():
                isMax2 = None
            else:
                isMax2 = self.__checkMax(i2, self.Vlocal[streamID],
                                         self.Vmaxt[streamID],
                                         self.signV[streamID], 1,
                                         pos, self.idx[streamID],
                                         self.sps[streamID],
                                         lowThresh=3 * self.rms[streamID])

            # If we find a maximum add it to results
            if (isMax is not None) and (self.pReal[streamID] is not None):
                res.append(isMax)

            # If we find a maximum in the filtered signal, add it to results
            if isMax2 is not None:
                # If the P arrival was still not detected, now it is done!
                if self.pReal[streamID] is None:
                    self.pReal[streamID] = isMax2[0]

                res2.append(isMax2)
                self.posLastPeak[streamID] = isMax2[0]
                self.stage[streamID] = 1
                dur[streamID] = isMax2.time - res2[0].time
            else:
                if self.pReal[streamID] is not None:
                    self.stage[streamID] = max(2, self.stage[streamID])
                    # Check whether the 60 seconds are already gone
                    if (relTime - self.posLastPeak[streamID]) >= 60.0:

                        if self.posLastPeak[streamID]:
                            # Calculate the duration as the difference between
                            # the last peak and the first peak detected in the
                            # HF filtered signal.
                            dur[streamID] = res2[-1].time - res2[0].time

                        else:
                            # No peak was detected
                            print 'DEBUG!', streamID, relTime
                            return False

                        sys.stdout.flush()
                        self.stage[streamID] = 3

                        # Remove the peaks in the raw signal that go beyond the
                        # "duration" of the event
                        # res = [p for p in res if p[0] <= res2[-1][0]]

                        return True

            # Write filtered streams to file
            auxValues.append((relTime, data2.get(pos)))

        # Write the filtered data to a file
        self.__save2File("%s-%s%s%s%s-f.dat" % (self.name, n, s, l, c),
                         auxValues, 'a')

        # Update the index count
        self.idx[streamID] = self.idx[streamID] + nsamp

        return True

    def __save2File(self, filename, values, mode='w'):
        with open(filename, mode) as fstr:
            if not isinstance(values, Iterable):
                fstr.write('%s ' % values)
            else:
                for line in values:
                    if not isinstance(line, Iterable):
                        fstr.write('%s ' % line)
                    else:
                        for value in line:
                            fstr.write('%s ' % value)
                        fstr.write('\n')

    def __removeFiles(self, filePatt):
        r = glob.glob(filePatt)
        for i in r:
            try:
                os.remove(i)
            except:
                pass

    def __saveResult(self):
        # This method should be called to save the original signal, the
        # filtered signal and the peaks recognized.
        if not self.dumpWaveforms:
            return

        # Remove all files with peaks and magnitudes
        self.__removeFiles("%s-*-p.dat" % (self.name))
        self.__removeFiles("%s-*-p2.dat" % (self.name))
        self.__removeFiles("%s-*-m.dat" % (self.name))

        for streamID in self.results:
            # If there were gaps or other problems while receiving data
            if streamID in self._wrongStreams:
                continue

            n, s, l, c = streamID.split('.')

            # Save the peaks detected in the raw signal
            self.__save2File("%s-%s%s%s%s-p.dat" % (self.name, n, s, l, c),
                             self.results[streamID], 'w')

            # Save the peaks detected in the filtered signal
            self.__save2File("%s-%s%s%s%s-p2.dat" % (self.name, n, s, l, c),
                             self.results2[streamID], 'w')

            # Save the magnitude from this stream
            self.__save2File("%s-%s%s%s%s-m.dat" % (self.name, n, s, l, c),
                             self.magnitude[streamID], 'w')

        return

    def update(self):
        """Method to give partial results about magnitude calculation
        A bool value should be returned:
            True: We need to process further
            False: Magnitude is already processed
        """

        # List with all magnitudes from streams
        magnitudes = []

        # To shorten notation
        sMag = self.magnitude

        modStage = 3

        simTime = max(self._timeStream.values()) - self.event.timeSC3 if \
            len(self._timeStream) else 0.0
        mHara = []
        for streamID in self.results:
            n, s, l, c = streamID.split('.')
            pArrival = self.timeWinDict[n, s, l, c][0] + \
                seiscomp3.Core.TimeSpan(self.margin_begin +
                                        self.peepAvg -
                                        self.startTime[streamID])
            #maxUnknDur = max((self._timeStream[streamID] - pArrival).length(),
            #                 maxUnknDur)
            if (self.Vmaxt[streamID][0].time > pArrival.length()):
                mHara.append((self.Vmaxt[streamID][0].time -
                              pArrival.length()))
        mHara.sort()
        mHaraValue = mHara[int(round((len(mHara) - 1) * 0.75))] if len(mHara)\
            else 0

        auxList = []
        auxList2 = []
        topStreams = set()
        for streamID in self.duration:
            # Discard streams with gaps or discontinuities
            if streamID in self._wrongStreams:
                continue

            if ((self.duration[streamID] > 0.8 * self.meanDuration) or
                    (self.stage[streamID] == 3)):
                auxList2.append((self.duration[streamID], streamID,
                                self.idx[streamID]))
                auxList.append(self.duration[streamID])
                topStreams.add(streamID)

        # Calculate a common duration based on the value located in the 50 % of
        # the order values
        auxList.sort()
        auxList2.sort()
        self.meanDuration = auxList[int(round((len(auxList) - 1) * 0.5))]\
            if len(auxList) else mHaraValue

        status = 'Status: Peaks %d, Peaks2 %d, Dur %d, Hara %3.1f (%d)' %\
            (len(self.results), len(self.results2), len(auxList),
             mHaraValue, len(mHara))
        #print [(n[2] / self.sps[streamID], n[1], '%.1f' % round(n[0], 1))
        #       for n in auxList2]

        for streamID in self.results:
            # If there were gaps or other problems while receiving data
            if streamID in self._wrongStreams:
                continue

            n, s, l, c = streamID.split('.')

            if streamID in self.pReal and self.pReal[streamID] is not None:
                pArrival = self.pReal[streamID]
            else:
                pArrival = self.timeWinDict[n, s, l, c][0] + \
                    seiscomp3.Core.TimeSpan(self.margin_begin +
                                            self.peepAvg -
                                            self.startTime[streamID])
                pArrival = pArrival.length()

            # Temporary end of event (duration) from the recognized peaks in
            # the (HF) filtered signal and the mean duration from all the
            # streams.
            limit = pArrival + self.meanDuration

            # Check whether the end of the event was found
            if self.stage[streamID] == 1:
                msg = '%s: End of event not found!' % streamID
                seiscomp3.Logging.warning(msg)

            # Check whether the magnitude should be still calculated for some
            # streamID
            modStage = min(modStage, self.stage[streamID])

            sMag[streamID] = 0.0

            for p in self.results[streamID]:
                sMag[streamID] += (abs(p.value) / 2.0 if limit is not None and
                                   p.before(limit) else 0)

            sMag[streamID] = log10(sMag[streamID] / (2 * pi)) \
                if (sMag[streamID] > 0.0) else 0.0

            # Distance calculation
            sta = self.filtered[n, s]
            delta, az, baz = seiscomp3.Math.delazi(self.event.lat,
                                                   self.event.lon,
                                                   sta.latitude(),
                                                   sta.longitude())

            # The final magnitude includes also an extra term depending
            # on the distance of the station and the depth of the event
            sMag[streamID] += Q_PV(delta, self.event.dep)

            # Save also in a list of magnitudes to be worked further
            if streamID in topStreams:
                magnitudes.append((sMag[streamID], self.duration[streamID] if
                                   streamID in self.duration else 0.0,
                                   streamID))

        # Discard 25 % of the values
        magnitudes.sort()
        lowlim = int(len(magnitudes) * 0.125)

        magnitudes = magnitudes[lowlim: (-lowlim if lowlim else None)]
        finalMag = sum([m[0] for m in magnitudes]) / float(len(magnitudes)) \
            if len(magnitudes) else 0

        print '%s %4.1f %3.2f %3.2f %d streams %s' % (self.name,
                                                      simTime, finalMag,
                                                      self.meanDuration,
                                                      len(magnitudes),
                                                      status)

        self.__save2File("%s.txt" % self.name, magnitudes, 'w')

        if modStage == 3:
            return False

        return True

    def finalize(self):
        # FIXME Some of these tasks could be moved to feed. For instance,
        # the magnitude, which should be stored in an attribute of the
        # class.

        # List with all magnitudes from streams
        magnitudes = []

        # To shorten notation
        sMag = self.magnitude

        auxList = []
        for streamID in self.duration:
            if self.duration[streamID]:
                auxList.append(self.duration[streamID])

        # Calculate a common duration based on the value located in the 50 % of
        # the order values
        auxList.sort()
        if len(auxList) > 5:
            self.meanDuration = auxList[int((len(auxList) - 1) * 0.5)]
        else:
            self.meanDuration = sum(auxList) / len(auxList) if len(auxList) \
                else 1.0

        for streamID in self.results:
            # If there were gaps or other problems while receiving data
            if streamID in self._wrongStreams:
                continue

            n, s, l, c = streamID.split('.')

            if streamID in self.pReal and self.pReal[streamID] is not None:
                pArrival = self.pReal[streamID]
            else:
                pArrival = self.timeWinDict[n, s, l, c][0] + \
                    seiscomp3.Core.TimeSpan(self.margin_begin +
                                            self.peepAvg -
                                            self.startTime[streamID])
                pArrival = pArrival.length()

            limit = pArrival + self.meanDuration

            # Remove the peaks outside the "duration" of the event
            self.results[streamID] = [p for p in self.results[streamID]
                                      if p.before(limit)]

            # Check whether the end of the event was found
            if self.stage[streamID] == 1:
                msg = '%s: End of event not found!' % streamID
                seiscomp3.Logging.warning(msg)

            sMag[streamID] = 0.0

            for p in self.results[streamID]:
                sMag[streamID] += (abs(p.value) / 2.0 if limit is not None and
                                   p.before(limit) else 0)

            sMag[streamID] = log10(sMag[streamID] / (2 * pi)) if \
                (sMag[streamID] > 0.0) else 0.0

            # Distance calculation
            sta = self.filtered[n, s]
            delta, az, baz = seiscomp3.Math.delazi(self.event.lat,
                                                   self.event.lon,
                                                   sta.latitude(),
                                                   sta.longitude())

            # The final magnitude includes also an extra term depending
            # on the distance of the station and the depth of the event
            sMag[streamID] += Q_PV(delta, self.event.dep)

            # Save also in a list of magnitudes to be worked further
            magnitudes.append((sMag[streamID], self.duration[streamID] if
                               streamID in self.duration else 0.0, streamID))

        # Discard 25 % of the values
        magnitudes.sort()
        lowlim = int(len(magnitudes) * 0.125)

        magnitudes = magnitudes[lowlim:-lowlim]

        finalMag = 0.0
        for ms in magnitudes:
            finalMag += (ms[0] / float(len(magnitudes))) if len(magnitudes) \
                else 0

        print '%s(final) Mag(avg): %3.2f Dur(3/4): %3.2f (%d streams)' % \
            (self.name, finalMag, self.meanDuration, len(magnitudes))

        self.__save2File("%s.txt" % self.name, magnitudes, 'w')

        # Delete results from previous run to be able to save new results
        if self.dumpWaveforms:
            self.__saveResult()

        return

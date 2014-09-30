import os
import glob
import seiscomp3.Math
import seiscomp3.Logging


class Event:
    def __init__(self, time, lat, lon, dep):
        self.time = time.toString("%Y-%m-%d %H:%M:%S.%f000000")[:22]
        self.timeSC3 = time
        self.lat = lat
        self.lon = lon
        self.dep = dep


class Processor:
    def __init__(self, dumpWaveforms=False):
        self.event = None
        self.gain = dict()
        self.filtered = dict()
        self.dumpWaveforms = dumpWaveforms

        # Timewindows requested
        self.timeWinDict = dict()

        # Samples/second
        self.sps = dict()

        # Record when the timewindow actually starts
        self.startTime = dict()

        # Average value for this stream to be used to center the signal inc ase
        # of a wrong offset
        self.avgValue = dict()

        # Number of seconds from the beginning of the signal to be used in the
        # calculation of the average value.
        self.peepAvg = 20

        # To check the proper order of records and possible gaps
        self._timeStream = dict()

        # List of accepted incoming records for each stream
        self._incoming = dict()

        # List of streams whose records will be rejected because they have
        # gaps or are not in chronological order
        self._wrongStreams = []

    def timeWindows(self, rec):
        """This method MUST be implemented in the derived class."""

        pass

    def feed(self, rec):
        """Only check that the record is inside the requested timewindow."""

        # Read the streamID
        streamID = rec.streamID()
        n, s, l, c = streamID.split('.')

        # Check if the record belongs to an already discarded stream
        if streamID in self._wrongStreams:
            # Delete files containing incomplete data ONLY if we are storing
            # data in this run. Otherwise we could delete files from a previous
            # run.
            if self.dumpWaveforms:
                test = '%s-%s%s%s%s*' % (self.name, n, s, l, c)
                r = glob.glob(test)
                for i in r:
                    try:
                        os.remove(i)
                    except OSError:
                        pass
            return False

        # Check that the beginning of the record (+30 seconds) is inside the
        # timewindow
        if (n, s, l, c) in self.timeWinDict:
            t_from, t_to = self.timeWinDict[n, s, l, c]
            rStart = rec.startTime()
            rEnd = rec.endTime()
            if not ((rStart > t_to) or (rEnd < t_from)):
                if not streamID in self._timeStream:
                    # The start time of the record is kept in order to check
                    # that the records come in order. I tried keeping end time
                    # and compare it with the start time of the next one but
                    # there is a minimum overlapping.
                    self.startTime[streamID] = rStart.length()
                    self._timeStream[streamID] = rEnd
                    self._incoming[streamID] = [rec]
                    self.sps[streamID] = rec.samplingFrequency()
                else:
                    # Check that the new record comes in chronological order
                    if rEnd < self._timeStream[streamID]:
                        msg = "Record in wrong order! %s : '%s' before '%s'" \
                            % (streamID, rEnd,
                               self._timeStream[streamID])
                        seiscomp3.Logging.error(msg)
                        self._wrongStreams.append(streamID)
                        return False

                    # Check that there is no gap longer than 5 seconds
                    if (rStart > (self._timeStream[streamID] +
                                  seiscomp3.Core.TimeSpan(5))):
                        msg = "Gap between records! %s : '%s' till '%s'" % \
                            (streamID, self._timeStream[streamID],
                             rStart)
                        seiscomp3.Logging.error(msg)
                        self._wrongStreams.append(streamID)
                        return False
                    else:
                        self._timeStream[streamID] = rEnd
                        self._incoming[streamID].append(rec)

                # If the record was appended see whether I need to calculate
                # the average.
                if (streamID not in self.avgValue):
                    self.avgValue[streamID] = (0, 0)

                # If I have a tuple here, this means that I still need to
                # calculate further the average
                if type(self.avgValue[streamID]) == tuple:
                    limitTime = self.startTime[streamID] + self.peepAvg
                    limitPos = (limitTime - rStart.length()) * \
                        rec.samplingFrequency()

                    gain = self.getGain(n, s, l, c)
                    cumul, count = self.avgValue[streamID]

                    # Loop to calculate the average
                    data = rec.data().numpy()
                    for pos, i in enumerate(data):
                        cumul += i / gain
                        count += 1
                        if pos > limitPos:
                            # I'm done calculating the average!
                            self.avgValue[streamID] = cumul / count
                            break
                    else:
                        # I still need the next record to calculate the average
                        self.avgValue[streamID] = (cumul, count)

                return True

        return False

    def setInventory(self, inventory):
        print "This should not be called!!!!"
        seiscomp3.Logging.debug("Processor %s: setInventory %d items" %
                                (self.name, len(inventory)))
        self.inventory = inventory

    def getGain(self, net, sta, loc, cha):
        if (net, sta, loc, cha) not in self.gain:
            s = self.filtered[net, sta, loc, cha]
            # From meters to nanometers
            self.gain[net, sta, loc, cha] = s.gain() * 1E-9
            if not self.gain[net, sta, loc, cha]:
                self.gain[net, sta, loc, cha] = 1.0
        return self.gain[net, sta, loc, cha]

    def setEvent(self, origin):
        # event is a SC3 event!
        updateRequired = False
        lat = origin.latitude().value()
        lon = origin.longitude().value()
        dep = origin.depth().value()
        # time = origin.time().value().toString(
        #    "%Y-%m-%d %H:%M:%S.%f000000")[:22]
        time = origin.time().value()

        if self.event:
            delta, az, baz = seiscomp3.Math.delazi(self.event.lat,
                                                   self.event.lon,
                                                   lat, lon)
            dz = abs(dep - self.event.dep)
            if delta > 0.05 or dz > 5:
                updateRequired = True

        self.event = Event(time=time, lat=lat, lon=lon, dep=dep)
        seiscomp3.Logging.debug("Processor %s: setEvent %s %.2f %.2f %.0f"
                                % (self.name,
                                   self.event.time,
                                   self.event.lat,
                                   self.event.lon,
                                   self.event.dep))

        if updateRequired:
            self.update()

    def update(self):
        pass

    def finalize(self):
        seiscomp3.Logging.debug("Processor %s: finalizing" % self.name)

#! /usr/bin/env python

import sys
import fnmatch
import traceback
import seiscomp3.Client

# every so many seconds updates are computed on newly available data
timerIntervalSeconds = 1

# magnitudeModules = ["mBc", "otherMagnitudes"]
magnitudeModules = ["mBc"]
magnitudeModules = {m: __import__(m) for m in magnitudeModules}


class AcquiApp(seiscomp3.Client.StreamApplication):

    def __init__(self, argc, argv):
        """ Python-level init() """
        seiscomp3.Client.StreamApplication.__init__(self, argc, argv)
        self.setDatabaseEnabled(True, True)
        self.setLoadInventoryEnabled(True)
        self.setLoggingToStdErr(True)
        self.setDaemonEnabled(False)
        self.setRecordStreamEnabled(True)

        self.setMessagingEnabled(False)
        self.addMessagingSubscription("EVENT")
        self.addMessagingSubscription("LOCATION")
        self.addMessagingSubscription("MAGNITUDE")

    def init(self):
        """ SC3-level init() """
        if not seiscomp3.Client.StreamApplication.init(self):
            return False

        self._cache = seiscomp3.DataModel.PublicObjectRingBuffer(self.query(),
                                                                 1000)

        try:
            self.eventID = self.commandline().optionString("event")
        except:
            sys.stderr.write("You must specify event id\n")
            return False

        self._blacklist = []
        try:
            blacklist = self.commandline().optionString("blacklist")
            for line in file(blacklist).xreadlines():
                self._blacklist.append(line.strip())
        except IOError:
            sys.stderr.write("Couldn't read blacklist file '%s'\n" % blacklist)
            return False
        except:
            pass
        for item in self._blacklist:
            seiscomp3.Logging.info(item)

        try:
            self._initializeProcessing()
        except Exception, exc:
            sys.stderr.write("ERROR in init(): " + str(exc) + "\n")
            return False

        # FIXME ???
        if timerIntervalSeconds:
            self.enableTimer(timerIntervalSeconds)

        return True

    def createCommandLineDescription(self):
        try:
            try:
                self.commandline().addGroup("Processing")
                msg = "ID of event to process"
                self.commandline().addStringOption("Processing",
                                                   "event,E", msg)

                self.commandline().addGroup("Input")
                msg = "input format to use (xml [default], zxml (zipped " + \
                    "xml), binary)"
                self.commandline().addStringOption("Input", "format,f", msg)

                msg = "input file, default: stdin"
                self.commandline().addStringOption("Input", "input,i", msg)

                self.commandline().addGroup("Control")
                msg = "stream blacklist"
                self.commandline().addStringOption("Control", "blacklist,b",
                                                   msg)

                self.commandline().addGroup("Debugging")
                msg = "Save the requested waveforms in ASCII format"
                self.commandline().addOption("Control",
                                             "dump-waveforms,w", msg)
            except:
                seiscomp3.Logging.warning("caught unexpected error %s"
                                          % sys.exc_info())
            return True
        except:
            info = traceback.format_exception(*sys.exc_info())
            for i in info:
                sys.stderr.write(i)
            sys.exit(-1)

    # FIXME ???
    def validateParameters(self):
        try:
            if (seiscomp3.Client.StreamApplication.validateParameters(self)
                    is False):
                return False
            if not self.commandline().hasOption("event"):
                self.setDatabaseEnabled(False, False)
            return True
        except:
            info = traceback.format_exception(*sys.exc_info())
            for i in info:
                sys.stderr.write(i)
            sys.exit(-1)

    def _loadEvent(self, eventID):
        """Retrieve event information based on eventID and the
        preferred origin."""

        evt = self.query().loadObject(seiscomp3.DataModel.Event.TypeInfo(),
                                      eventID)
        evt = seiscomp3.DataModel.Event.Cast(evt)
        if evt is None:
            raise TypeError("unknown event '" + eventID + "'")

        originID = evt.preferredOriginID()
        org = self.query().loadObject(seiscomp3.DataModel.Origin.TypeInfo(),
                                      originID)
        org = seiscomp3.DataModel.Origin.Cast(org)
        if not org:
            seiscomp3.Logging.error("origin '%s' not loaded" % originID)
            return

        self.evt = evt
        self.org = org

    def _blacklisted(self, stream_id):
        """Check whether the stream should be discarded"""

        for pattern in self._blacklist:
            if fnmatch.fnmatch(stream_id, pattern):
                return True
        return False

    def _prepareInventory(self, time):
        self._inventory = dict()

        # Retrieve a network list from the SeisComP3 inventory
        inv = seiscomp3.Client.Inventory.Instance().inventory()
        nnet = inv.networkCount()
        for inet in xrange(nnet):
            network = inv.network(inet)
            net = network.code()
            self._inventory[net] = network
            nsta = network.stationCount()
            for ista in xrange(nsta):
                station = network.station(ista)

                # Check that the station was operational at the specified time
                try:
                    if not station.start() < time < station.end():
                        continue
                except:
                    # FIXME Why pass? Maybe better continue
                    pass

                sta = station.code()
                self._inventory[net, sta] = station

                # now we know that this is an operational station
                for iloc in xrange(station.sensorLocationCount()):
                    location = station.sensorLocation(iloc)
                    try:
                        if not location.start() < time < location.end():
                            continue
                    except:
                        # FIXME Why pass? Maybe better continue
                        pass

                    loc = location.code()
                    self._inventory[net, sta, loc] = location

                    for istr in range(location.streamCount()):
                        stream = location.stream(istr)
                        try:
                            if not stream.start() < time < stream.end():
                                continue
                        except:
                            # FIXME Why pass? Maybe better continue
                            pass

                        cha = stream.code()
                        stream_id = ".".join((net, sta, loc, cha))

                        # Check whether the stream should be discarded
                        if self._blacklisted(stream_id):
                            seiscomp3.Logging.warning("blacklisted %s"
                                                      % stream_id)
                        else:
                            self._inventory[net, sta, loc, cha] = stream

        return self._inventory

    def _initializeProcessing(self):
        self._loadEvent(self.eventID)

        # XXX
        now = seiscomp3.Core.Time.GMT()
        self._prepareInventory(now)

        return

    def _requestWaveforms(self, waveform_windows):
        """Based on the timewindows received as a parameter, those are
        requested."""

        # NOTE that this MUST be done from within init() in order to
        # automatically ("magically") start the acquisition after
        # init() returns.

        try:
            self.setRecordInputHint(seiscomp3.Core.Record.SAVE_RAW)
            stream = self.recordStream()
            stream.setTimeout(3600)
            for t_from, t_to, net, sta, loc, cha in waveform_windows:
                stream.addStream(net, sta, loc, cha, t_from, t_to)
        except:
            info = traceback.format_exception(*sys.exc_info())
            for i in info:
                sys.stderr.write(i)

    def handleClose(self):
        # FIXME Does _updateProcessing need to be called/exist?
        self._updateProcessing()
        self._finalizeProcessing()
        return True

    def handleTimeout(self):
        self._updateProcessing()

    def handleRecord(self, rec):
        # Check whether stream is new and prepare a list to store data if
        # necessary
        streamID = rec.streamID()
        n, s, l, c = streamID.split('.')

        # Check whether the record is accepted by at least one module
        accepted = False
        # Call the magnitude calculator modules with the received record
        for name in self._processor:
            processor = self._processor[name]
            # If the module accepted the record, this is saved in "accept"
            accepted = accepted or processor.feed(rec)

        return accepted

    def addObject(self, parentID, obj):
        try:
            evt = seiscomp3.DataModel.Event.Cast(obj)
            if evt and evt.publicID() == self.eventID:
                self.evt = evt
                seiscomp3.Logging.debug("got new event '%s'" % evt.publicID())
                return
            org = seiscomp3.DataModel.Origin.Cast(obj)
            if org:
                self._cache.feed(org)
                seiscomp3.Logging.debug("got new origin '%s'" % org.publicID())
                for name in self._processor:
                    processor = self._processor[name]
                    processor.setEvent(org)
                return
            mag = seiscomp3.DataModel.Magnitude.Cast(obj)
            if mag:
                self._cache.feed(mag)
                seiscomp3.Logging.debug("got new magnitude '%s'"
                                        % mag.publicID())
                return
        except:
            info = traceback.format_exception(*sys.exc_info())
            for i in info:
                sys.stderr.write(i)

    def updateObject(self, parentID, obj):
        # FIXME This should be taken into account to recompute the magnitude if
        # an origin changes
        try:
            evt = seiscomp3.DataModel.Event.Cast(obj)
            if evt and evt.publicID() == self.eventID:
                self.evt = evt
                self.org = self._cache.get(seiscomp3.DataModel.Origin,
                                           evt.preferredOriginID())
                # agencyID = self.org.creationInfo().agencyID()
                seiscomp3.Logging.debug("update event '%s'" %
                                        self.evt.publicID())
                seiscomp3.Logging.debug("preferred origin is now '%s'" %
                                        self.org.publicID())
                return
            mag = seiscomp3.DataModel.Magnitude.Cast(obj)
            if mag:
                self._cache.feed(mag)
                seiscomp3.Logging.debug("update magnitude '%s'" %
                                        mag.publicID())
                return
        except:
            info = traceback.format_exception(*sys.exc_info())
            for i in info:
                sys.stderr.write(i)


class ProcessorApp(AcquiApp):

    def init(self):
        AcquiApp.init(self)

        timeWin = []

        self._processor = dict()
        for name in magnitudeModules:
            # To shorten notation
            mm = magnitudeModules[name]
            processor = self._processor[name] = mm.Processor(
                self.commandline().hasOption("dump-waveforms"))
            if hasattr(self, "org"):
                processor.setEvent(self.org)
            else:
                sys.exit(-2)
            processor._filterInventory(self._inventory)

            processor.timeWindows()
            for net, sta, loc, cha in processor.timeWinDict:
                t_from, t_to = processor.timeWinDict[net, sta, loc, cha]
                timeWin.append((t_from, t_to, net, sta, loc, cha))

        # We do not need inventory as a filtered version exist in every
        # magnitude module
        self._inventory = dict()
        AcquiApp._requestWaveforms(self, timeWin)

        return True

    def _updateProcessing(self):
        # This is where the actual waveform processing is delegated to the
        # individual magnitude modules.
        seiscomp3.Logging.debug("_updateProcessing begin")
        # for streamID in self._incoming:
        #     n = len(self._incoming[streamID])
        #     if n < 10: continue # XXX review
        #     seiscomp3.Logging.debug("_updateProcessing %-20s %6d new records"
        #     % (streamID,n))

        # Call update in every magnitude calculator module
        for name in self._processor:
            processor = self._processor[name]
            processor.update()

        seiscomp3.Logging.debug("_updateProcessing end")

    def _finalizeProcessing(self):
        seiscomp3.Logging.debug("_finalizeProcessing begin")
        for name in self._processor:
            processor = self._processor[name]
            # Check that this is OK here
            processor.finalize()

        seiscomp3.Logging.debug("_finalizeProcessing end")

    def handleRecord(self, rec):
        AcquiApp.handleRecord(self, rec)


def main():
    app = ProcessorApp(len(sys.argv), sys.argv)
    app()


if __name__ == "__main__":
    main()

========================
scxxlmag v1.0RC1 - README
========================
:Author: Javier Quinteros <javier@gfz-potsdam.de>, Joachim Saul <saul@gfz-potsdam.de>
:Info: The User Guide can be downloaded from <https://github.com/SeisComP3/NERA/scxxlmag/scxxlmag.pdf>.
:Version: 1.0-RC1

Functionality
=========

The *scxxlmag* is a SeisComP3 module developed by `Javier Quinteros`_ and `Joachim Saul`_ in the context of the `NERA`_ project. Its main purpose is to be able to calculate the |mBc| magnitude for large earthquakes in real-time. The present revision of the software includes the following functionality:

* Receive information about an event from a |SC3| server.
* Request all the waveforms needed to perform the calculation.
* Calculate the rupture duration while the information is being received.
* Calculate the magnitude while the information is being received.
* Send updates of the (preliminary) magnitude value and rupture duration at regular intervals
* Generate graphs showing the temporal evolution of the magnitude and rupture duration for a particular event

Setup
=====

Installation
------------

The latest version of *scxxlmag* can be downloaded from a `GitHub respository <https://github.com/SeisComP3/NERA>`_ under the official repository of |SC3|. 

Dependencies
^^^^^^^^^^^^

* *Python* >= 2.6 (2.7 would be better)
* |SC3| release *Seattle* or newer (e.g. *Jakarta*)
* *seispy* tools from `Joachim Saul`_ (https://github.com/jsaul) is needed and should be in the Python path.

Running the application
=======================

Setting the environment
-----------------------

The |SC3| variables should be already in the session environment. You can load the necessary variables by executing::

    user@hostname ~/scxxlmag $ ~/seiscomp3/bin/seiscomp print env

and then copy-paste the output of the previous command in the console. For instance,::

    user@hostname ~/scxxlmag $ export SEISCOMP_ROOT=/home/user/seiscomp3
    user@hostname ~/scxxlmag $ export PATH=/home/user/seiscomp3/bin:$PATH
    user@hostname ~/scxxlmag $ export LD_LIBRARY_PATH=/home/user/seiscomp3/lib:LD_LIBRARY_PATH
    user@hostname ~/scxxlmag $ export PYTHONPATH=/home/user/seiscomp3/lib/python:$PYTHONPATH
    user@hostname ~/scxxlmag $ export MANPATH=/home/user/seiscomp3/share/man:$MANPATH
    user@hostname ~/scxxlmag $ export LC_ALL=C

Calling the application
-----------------------

The application can be run by executing::

    user@hostname ~/scxxlmag $ ./scxxlmag-compute.py

A file called ``scxxlmag.sh`` is provided as an example of how the application can be called with some of the most common options.

Contacts
========

* Javier Quinteros <javier@gfz-potsdam.de>

* Joachim Saul <saul@gfz-potsdam.de>

.. rubric:: Footnotes

.. [#r1] Bormann, Peter and Saul, Joachim (2009) “A Fast, Non-saturating Magnitude Estimator for Great Earthquakes”, Seismological Research Letters, 80: 808-816, doi:10.1785/gssrl.80.5.808


.. |mBc| replace:: m\ :sub:`Bc`
.. |SC3| replace:: SeisComP3
.. |JS| replace:: Joachim Saul <http:/sarasa.com>

.. _Javier Quinteros: http://www.gfz-potsdam.de/en/research/organizational-units/departments/department-2/seismology/staff/profil/javier-quinteros/
.. _Joachim Saul: http://www.gfz-potsdam.de/en/research/organizational-units/departments/department-2/seismology/staff/profil/joachim-saul/
.. _NERA: http://www.nera-eu.org/

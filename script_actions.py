from contextlib2 import contextmanager

from future.moves import itertools
from math import tan, radians, sin
from datetime import datetime

from six.moves import input

try:
    # pylint: disable=import-error
    from genie_python import genie as g
except ImportError:
    from mocks import g

# import general.utilities.io
from sample import Sample
from NR_motion import _Movement
from instrument_constants import get_instrument_constants


class DryRun:
    dry_run = False
    counter = 0
    run_time = 0

    def __init__(self, f):
        self.f = f

    def __call__(self, *args, **kwargs):
        if self.__class__.dry_run:
            DryRun.counter += 1

            DryRun.run_time += self.f(*args, **kwargs, dry_run=True)
            hours = str(int(DryRun.run_time / 60)).zfill(2)
            minutes = str(int(DryRun.run_time % 60)).zfill(2)
            tit = args[0].title if isinstance(args[0], Sample) else ""
            if self.counter <=1:
                columns = ["No", "Action", "Title", "Parameters", "Duration"]
                print(f"{columns[0]:^11}|{columns[1]:^17}|{columns[2]:^52}|{columns[3]:^19}|{columns[4]:^16}")

            if tit != "":
                # print(f'{DryRun.counter:02}', "Dry run: ",
                #       self.f.__name__, tit, args[1:], "-->|", hours + ":" + minutes, " hh:mm")
                arg = str(args[1:])
                print(f"{DryRun.counter:02} Dry run: {str(self.f.__name__)[:15]:17} "
                      f"{tit[:50]:52} {arg[:15]:17} -->| {hours:2}:{minutes:2}  hh:mm")
            else:
                # print(f'{DryRun.counter:02}', "Dry run: ",
                #       self.f.__name__, kwargs, "-->|", hours + ":" + minutes, "hh:mm")
                print(f"{DryRun.counter:02} Dry run: {self.f.__name__} {kwargs[50]:52} "
                      f"-->| {hours:2}:{minutes:2} hh:mm")
        else:
            print("Running for real...")
            self.f(*args, **kwargs)


class ScriptActions:
    @DryRun
    def run_angle(sample, angle: float, count_uamps: float = None, count_seconds: float = None,
                  count_frames: float = None, vgaps: dict = None, hgaps: dict = None, mode: str = None,
                  dry_run: bool = False, include_gaps_in_title: bool = False, osc_slit: bool = False,
                  osc_block: str = 'S2HG', osc_gap: float = None):
        """
        Move to a given theta and smangle with slits set. If a current, time or frame count are given then take a
        measurement.
        Both supermirrors removed and all angle axes enabled.

        Args:
            sample (techniques.reflectometry.sample.Sample): The sample to measure
            angle: The angle to measure at, theta and in liquid mode also the sm angle
            count_uamps: the current to run the measurement for; None for use count_seconds
            count_seconds: the time to run the measurement for if uamps not set; None for use count_frames
            count_frames: the number of frames to wait for; None for don't count
            vgaps: vertical gaps to be set; Where not defined uses sample footprint and resolution
            hgaps: horizontal gaps to be set; Where not defined gap is unchanged
            mode: mode to run in; None don't change modes
            dry_run: If True just print what would happen; If False, run the experiment
            include_gaps_in_title: Whether current slit gap sizes should be appended to the run title or not
            osc_slit: whether slit oscillates during measurement; only osc if osc_gap < total gap extent setting.
            osc_block: block to oscillate
            osc_gap: gap of slit during oscillation. If None then takes defaults (see osc_slit_setup)
        TODO: this set of examples needs updating.
        Examples:
            The simplest scan is:
            >>> my_sample = Sample("My title", "my subtitle", 0, 0, 0, 0, 0, 0.6, 3.0)
            >>> run_angle(my_sample, 0.3, count_seconds=10)
            This will use my_sample settings to perform a measurement at the theta angle of 0.3 for 10 seconds. It will set
            slits 1 and 2 so that the resolution is 0.6 and the footprint is 3, then set slits 3 based on the fraction
            of the the maximum theta allowed. It will remove all supermirrors from the beam. The mode will not be
            changed and it will not use a height gun for auto-height mode.

            >>> run_angle(my_sample, 0.5, vgaps={'s1vg': 0.1, 's2vg' 0.3}, mode="Solid")
            In this evocation we are setting theta to 0.5 with s1 and s2 set to 0.1 and 0.3. The mode is also
            changed to Solid. Depending on what this means on your instrument this may also set the offsets for components
            back to 0. No count was specified so in this case the beamline is moved to the position and left there; no
            data is captured.

            >>> run_angle(my_sample, 0.0, dry_run=True)
            In this run, dry_run is set to True so nothing will actually happen, it will only print the settings that would
            be used for the run to the screen.
        """

        if dry_run:
            if count_uamps:
                return count_uamps / 40 * 60  # value for TS2, needs instrument check
            elif count_seconds:
                return count_seconds / 60
            elif count_frames:
                return count_frames / 36000
        else:
            print("** Run angle {} **".format(sample.title))

            movement = _Movement(dry_run)

            constants, mode_out = movement.setup_measurement(mode)

            movement.sample_setup(sample, angle, constants, mode_out)
            if hgaps is None:
                hgaps = sample.hgaps
            movement.set_axis_dict(hgaps)
            movement.set_slit_vgaps(angle, constants, vgaps, sample)
            movement.wait_for_move()
            movement.update_title(sample.title, sample.subtitle, angle, add_current_gaps=include_gaps_in_title)

            movement.start_measurement(count_uamps, count_seconds, count_frames, osc_slit, osc_block, osc_gap, vgaps,
                                       hgaps)

    @DryRun
    def run_angle_SM(sample, angle, count_uamps=None, count_seconds=None, count_frames=None, vgaps: dict = None,
                     hgaps: dict = None, smangle=0.0, mode=None, do_auto_height=False, laser_offset_block="b.KEYENCE",
                     fine_height_block="HEIGHT", auto_height_target=0.0, continue_on_error=False, dry_run=False,
                     include_gaps_in_title=False,
                     smblock='SM2', osc_slit: bool = False, osc_block: str = 'S2HG', osc_gap: float = None):
        """
        Move to a given theta and smangle with slits set. If a current, time or frame count are given then take a
        measurement.
        Behaviour depends on mode:
            If 'Liquid' then phi-psi do not move and smangle determined by theta.
            If not Liquid then phi-psi enabled and smangle is set via smangle Arg.

        Args:
            sample (techniques.reflectometry.sample.Sample): The sample to measure
            angle: The angle to measure at, theta and in liquid mode also the sm angle
            count_uamps: the current to run the measurement for; None for use count_seconds
            count_seconds: the time to run the measurement for if uamps not set; None for use count_frames
            count_frames: the number of frames to wait for; None for don't count
            vgaps: vertical gaps to be set; Where not defined uses sample footprint and resolution
            hgaps: horizontal gaps to be set; Where not defined gap is unchanged
            smangle: super mirror angle, place in the beam, if set to 0 remove from the beam; None don't move super mirror
            mode: mode to run in; None don't change modes
            do_auto_height: if True when taking data run the auto-height routine
            laser_offset_block: The block for the laser offset from centre
            fine_height_block: The block for the sample fine height
            auto_height_target: The target value for laser offset if using auto height
            continue_on_error: If True, continue script on error; If False, interrupt and prompt the user on error
            dry_run: If True just print what would happen; If False, run the experiment
            include_gaps_in_title: Whether current slit gap sizes should be appended to the run title or not
            smblock: prefix of supermirror block to be used; generally expect 'SM1' or 'SM2' for INTER or 'SM' for SURF.
                List of strings can be provided to use multiple mirrors.
            osc_slit: whether slit oscillates during measurement; only osc if osc_gap < total gap extent setting.
            osc_block: block to oscillate
            osc_gap: gap of slit during oscillation. If None then takes defaults (see osc_slit_setup)
        Examples:
            The simplest scan is:
            >>> my_sample = Sample("My title", "my subtitle", 0, 0, 0, 0, 0, 0.6, 3.0)
            >>> run_angle_SM(my_sample, 0.3, count_seconds=10)
            This will use my_sample settings to perform a measurement at the theta angle of 0.3 for 10 seconds. It will set
            slits 1 and 2 so that the resolution is 0.6 and the footprint is 3, then set slits 3 based on the fraction
            of the the maximum theta allowed. If liquid mode in IBEX it will calculate the supermirror angle to keep the
            sample flat, otherwise the super mirror will be moved out of the beam. It will not use a height gun for
             auto-height mode.

            >>> run_angle_SM(my_sample, 0.5, vgaps={'s1vg': 0.1, 's2vg': 0.3}, mode="Solid")
            In this evocation we are setting theta to 0.5 with s1 and s2 set to 0.1 and 0.3. The mode is also
            changed to Solid. Depending on what this means on your instrument this may also set the offsets for components
            back to 0. No count was specified so in this case the beamline is moved to the position and left there; no
            data is captured.

            >>> run_angle_SM(my_sample, 0.0, dry_run=True)
            In this run, dry_run is set to True so nothing will actually happen, it will only print the settings that would
            be used for the run to the screen.
        """

        print("** Run angle {} **".format(sample.title))

        movement = _Movement(dry_run)

        constants, mode_out = movement.setup_measurement(mode)
        smblock_out, smang_out = movement.sample_setup(sample, angle, constants, mode_out, smang=smangle,
                                                       smblock=smblock)

        if do_auto_height:
            _Movement.auto_height(laser_offset_block, fine_height_block, target=auto_height_target,
                                  continue_if_nan=continue_on_error, dry_run=dry_run)

        if hgaps is None:
            hgaps = sample.hgaps
        movement.set_axis_dict(hgaps)
        movement.set_slit_vgaps(angle, constants, vgaps, sample)
        movement.wait_for_move()

        movement.update_title(sample.title, sample.subtitle, angle, smang_out, smblock_out,
                              add_current_gaps=include_gaps_in_title)

        movement.start_measurement(count_uamps, count_seconds, count_frames, osc_slit, osc_block, osc_gap, vgaps, hgaps)

    # TODO: Do we want to change the order of the arguments here?
    @DryRun
    def transmission(sample, title: str, vgaps: dict = None, hgaps: dict = None, count_uamps: float = None,
                     count_seconds: float = None, count_frames: float = None, height_offset: float = 5,
                     mode: str = None, dry_run: bool = False, include_gaps_in_title: bool = True,
                     osc_slit: bool = True, osc_block: str = 'S2HG', osc_gap: float = None, at_angle: float = 0.7):
        """
        Perform a transmission with both supermirrors removed. Args: sample (techniques.reflectometry.sample.Sample): The
        sample to measure title: Title to set vgaps: vertical gaps to be set; for each gap if not specified then
        determined for angle at_angle hgaps: horizontal gaps to be set; for each gap if not specified then remains
        unchanged count_seconds: time to count for in seconds count_uamps: number of micro amps to count for
        count_frames: number of frames to count for height_offset: Height offset from normal to set the sample to (offset
        is in negative direction) mode: mode to run in; None don't change mode dry_run: If True just print what would
        happen; If False, run the transmission include_gaps_in_title: Whether current slit gap sizes should be appended
        to the run title or not osc_slit: whether slit oscillates during measurement; only osc if osc_gap < total gap
        extent setting. Takes extent from equivalent gap Args if exists otherwise, goes into defaults in osc_slit_setup.
        osc_block: block to oscillate osc_gap: gap of slit during oscillation. If None then takes defaults (see
        osc_slit_setup) at_angle: angle to calculate slit settings

        TODO: Need to update examples with oscillation.
        Examples:
            The simplest transmission is:

            >>> my_sample = Sample("My title", "my subtitle", 0, 0, 0, 0, 0, 0.6, 3.0) >>> transmission(my_sample,
            "My Title", count_seconds=1) This will set slit gaps 1 and 2 based on sample parameters. Slits 3 and 4 will
            be set to maximum vertical width. The horizontal slits will be left where they are. The height of the sample
            will be set to 5mm below the expected sample position. The super mirror will stay where it is and the mode
            won't change. After the run the horizontal slits will be set back to where they were when the move started.

            A more complicated example:
            >>> transmission(my_sample, "My Title", vgaps={"S1VG": 0.1, "S2VG": 0.2, "S3VG": 0.3}, count_frames=1,
            >>>              hgaps = {'s1hg': 20, 's2hg': 20, 's3hg': 20}, smangle=0.1, dry_run=True)
            Dry_run is true here so nothing will actually happen, but the effects will be printed to the screen. If
            dry_run had not been set then the vertical gaps would be set to 0.1, 0.2, 0.3 and 0.4, the horizontal gaps
            would be all set to 20. The super mirror would be moved into the beam and set to the angle 0.1.
            The system will be record at least 1 frame of data.
        """
        if dry_run:
            if count_uamps:
                return count_uamps / 40 * 60  # value for TS2, needs instrument check
            elif count_seconds:
                return count_seconds / 60
            elif count_frames:
                return count_frames / 36000
        else:
            print("** Transmission {} **".format(title))

            movement = _Movement(dry_run)
            constants, mode_out = movement.setup_measurement(mode)

            with _Movement.reset_hgaps_and_sample_height_new(movement, sample, constants):
                movement.sample_setup(sample, 0.0, constants, mode_out, height_offset)

                if vgaps is None:
                    vgaps = {}
                if "S3VG".casefold() not in vgaps.keys():
                    vgaps.update({"S3VG": constants.s3max})

                if hgaps is None:
                    hgaps = sample.hgaps
                movement.set_axis_dict(hgaps)
                movement.set_slit_vgaps(at_angle, constants, vgaps, sample)
                # Edit for this to be an instrument default for the angle to be used in calc when vg not defined.
                movement.wait_for_move()

                movement.update_title(title, "", None, add_current_gaps=include_gaps_in_title)
                movement.start_measurement(count_uamps, count_seconds, count_frames, osc_slit, osc_block, osc_gap, vgaps,
                                           hgaps)

                # Horizontal gaps and height reset by with reset_gaps_and_sample_height

    # TODO: Do we want to change the order of the arguments here?
    @DryRun
    def transmission_SM(sample, title: str, vgaps: dict = None, hgaps: dict = None,
                        count_uamps: float = None, count_seconds: float = None, count_frames: float = None,
                        height_offset: float = 5, smangle: float = 0.0,
                        mode: str = None, dry_run: bool = False, include_gaps_in_title: bool = True,
                        osc_slit: bool = True,
                        osc_block: str = 'S2HG', osc_gap: float = None, at_angle: float = 0.7,
                        smblock: str = 'SM2'):
        """
        Perform a transmission. Smangle is set via smangle Arg and the mirror can be specified.
        Behaviour depends on mode:
            If 'Liquid' then phi-psi do not move.
            If not Liquid then phi-psi enabled.
        Args:
            sample (techniques.reflectometry.sample.Sample): The sample to measure
            title: Title to set
            vgaps: vertical gaps to be set; for each gap if not specified then determined for angle at_angle
            hgaps: horizontal gaps to be set; for each gap if not specified then remains unchanged
            count_seconds: time to count for in seconds
            count_uamps: number of micro amps to count for
            count_frames: number of frames to count for
            height_offset: Height offset from normal to set the sample to (offset is in negative direction)
            smangle: super mirror angle, place in the beam, if set to 0 remove from the beam; None don't move super mirror
            mode: mode to run in; None don't change mode
            dry_run: If True just print what would happen; If False, run the transmission
            include_gaps_in_title: Whether current slit gap sizes should be appended to the run title or not
            osc_slit: whether slit oscillates during measurement; only osc if osc_gap < total gap extent setting. Takes extent
            from equivalent gap Args if exists otherwise, goes into defaults in osc_slit_setup.
            osc_block: block to oscillate
            osc_gap: gap of slit during oscillation. If None then takes defaults (see osc_slit_setup)
            at_angle: angle used in calculating slit settings
            smblock: prefix of supermirror block to be used; generally expect 'SM1' or 'SM2' for INTER or 'SM' for SURF.
                List of strings can be provided to use multiple mirrors.

        TODO: Need to update examples with oscillation.
        Examples:
            The simplest transmission is:

            >>> my_sample = Sample("My title", "my subtitle", 0, 0, 0, 0, 0, 0.6, 3.0)
            >>> transmission(my_sample, "My Title", 0.1, 0.2, count_seconds=1)
            This will set slit gaps 1 and 2 to 0.1 and 0.2. Slits 3 and 4 will be set to maximum vertical width. The
            horizontal slits will be left where they are. The height of the sample will be set to 5mm below the expected
            sample position. The super mirror will stay where it is and the mode won't change. After the run the horizontal
            slits will be set back to where they were when the move started.

            A more complicated example:
            >>> transmission(my_sample, "My Title", 0.1, 0.2, 0.3, 0.4, count_frames=1,
            >>>              s1hg=20, s2hg=20, s3hg=20, s4hg=20, smangle=0.1, mode="PNR", dry_run=True)
            Dry_run is true here so nothing will actually happen, but the effects will be printed to the screen. If
            dry_run had not been set then the vertical gaps would be set to 0.1, 0.2, 0.3 and 0.4, the horizontal gaps
            would be all set to 20. The super mirror would be moved into the beam and set to the angle 0.1. The mode will
            be changed to PNR. The system will be record at least 1 frame of data.
        """

        print("** Transmission {} **".format(title))

        movement = _Movement(dry_run)
        constants, mode_out = movement.setup_measurement(mode)

        with _Movement.reset_hgaps_and_sample_height_new(movement, sample, constants):

            smblock_out, smang_out = movement.sample_setup(sample, 0.0, constants, mode_out, height_offset, smangle,
                                                           smblock)

            if vgaps is None:
                vgaps = {}
            if "S3VG".casefold() not in vgaps.keys():
                vgaps.update({"S3VG": constants.s3max})
            if hgaps is None:
                hgaps = sample.hgaps
            movement.set_axis_dict(hgaps)
            movement.set_slit_vgaps(at_angle, constants, vgaps, sample)
            # Edit for this to be an instrument default for the angle to be used in calc when vg not defined.
            movement.wait_for_move()

            movement.update_title(title, "", None, smang_out, smblock_out, add_current_gaps=include_gaps_in_title)
            movement.start_measurement(count_uamps, count_seconds, count_frames, osc_slit, osc_block, osc_gap,
                                       vgaps, hgaps)

            # Horizontal gaps and height reset by with reset_gaps_and_sample_height

    # Added extra part for centres too.
    @contextmanager
    def reset_hgaps_and_sample_height_new(movement, sample, constants):
        """
        After the context is over reset the gaps back to the value before and set the height to the default sample height.
        Edited to reset the gap centres too.
        If keyboard interrupt give options for what to do.
        Args:
            movement(_Movement): object that does movement required (or pronts message for a dry run)
            sample: sample to get the sample offset from
            constants: instrument constants

        """
        horizontal_gaps = movement.get_gaps(vertical=False, centres=False)
        horizontal_cens = movement.get_gaps(vertical=False, centres=True)

        def _reset_gaps():
            print("Reset horizontal centres to {}".format(list(horizontal_cens.values())))
            movement.set_axis_dict(horizontal_cens)
            print("Reset horizontal gaps to {}".format(list(horizontal_gaps.values())))
            movement.set_axis_dict(horizontal_gaps)
            # TODO join the above together?

            movement.set_axis("HEIGHT", sample.height_offset, constants)
            movement.set_axis("HEIGHT2", sample.height2_offset, constants)
            movement.wait_for_move()

        try:
            yield
            _reset_gaps()
        except KeyboardInterrupt:
            running_on_entry = not movement.is_in_setup()
            if running_on_entry:
                g.pause()

            while True:
                print("")
                choice = input("ctrl-c hit do you wish to (A)bort or (E)nd or (K)eep Counting?")
                if choice is not None and choice.upper() in ["A", "E", "K"]:
                    break
                print("Invalid choice try again!")

            if choice.upper() == "A":
                if running_on_entry:
                    g.abort()
                print("Setting horizontal slit gaps to pre-tranmission values.")
                _reset_gaps()

            elif choice.upper() == "E":
                if running_on_entry:
                    g.end()
                _reset_gaps()

            elif choice.upper() == "K":
                print("Continuing counting, remember to set back horizontal slit gaps when the run is ended.")
                if running_on_entry:
                    g.resume()

            movement.wait_for_seconds(5)
            print("\n\n PRESS ctl + c to get the prompt back \n\n")  # This is because there is a bug in pydev
            raise  # reraise the exception so that any running script will be aborted

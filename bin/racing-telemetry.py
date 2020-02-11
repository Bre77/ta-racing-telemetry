from __future__ import print_function
from builtins import str
import sys
import xml.dom.minidom, xml.sax.saxutils
import time
import socket
import struct
import json
import logging
import re
import traceback

from forza_cars import forza_cars

#set up logging suitable for splunkd comsumption
logging.root
logging.root.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(levelname)s %(message)s')
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logging.root.addHandler(handler)

SCHEME = """<scheme>
    <title>Racing Telementry</title>
    <description>Get metrics from Racing video games over UDP.</description>
    <use_external_validation>false</use_external_validation>
    <streaming_mode>xml</streaming_mode>

    <endpoint>
        <args>
            <arg name="ratelimit">
                <title>Rate Limit</title>
                <description>Restrict the frequecy of data by restricting events from occuring for this time period in milliseconds.</description>
                <data_type>number</data_type>
            </arg>

            <arg name="port">
                <title>Port</title>
                <description>The UDP port to listen on</description>
                <data_type>number</data_type>
                <validation>is_avail_udp_port('port')</validation>
            </arg>

            <arg name="bindip">
                <title>Bind IP</title>
                <description>The IP address to listen on</description>
                <required_on_create>false</required_on_create>
                <data_type>string</data_type>
            </arg>

            <arg name="multimetric">
                <title>Metric Multi-Measurement</title>
                <description>Enable the Splunk 8 Multi-Measurement mode</description>
                <required_on_create>true</required_on_create>
                <data_type>boolean</data_type>
            </arg>

            <arg name="filtermenu">
                <title>Filter Menu</title>
                <description>Filters out data sent while in menu</description>
                <required_on_create>true</required_on_create>
                <data_type>boolean</data_type>
            </arg>

            <arg name="whitelist">
                <title>Telemetry Whitelist</title>
                <description>Regex to filter metrics</description>
                <required_on_create>true</required_on_create>
                <data_type>string</data_type>
            </arg>
        </args>
    </endpoint>
</scheme>
"""


#https://docs.google.com/spreadsheets/d/1bw6EAud8uDcZvSfvVv1bh1-dhiB5j6X6kyI31rHliIQ/edit?usp=sharing

pcars2_header = ["meta.PacketNumber","meta.CategoryPacketNumber","meta.PartialPacketIndex","meta.PartialPacketNumber","meta.PacketType","meta.PacketVersion"]
pcars2_weather = ["weather.Temperature.Ambient","weather.Temperature.Track","weather.RainDensity","weather.SnowDensity","weather.WindSpeed","weather.WindDirection.X","weather.WindDirection.Y"]
f1_2019_header = ["meta.PacketFormat","meta.Game.MajorVersion","meta.Game.MinorVersion","meta.packetVersion","meta.PacketNumber","meta.SessionUID","meta.SessionTime","meta.Frame","meta.PlayerIndex"]

labels = {
    "forza":         [None, "meta.Timestamp", "car.Rpm.Max", "car.Rpm.Idle", "car.Rpm.Current", "car.Acceleration.Local.X", "car.Acceleration.Local.Y", "car.Acceleration.Local.Z", "car.Velocity.Local.X", "car.Velocity.Local.Y", "car.Velocity.Local.Z", "car.Velocity.Angular.X", "car.Velocity.Angular.Y", "car.Velocity.Angular.Z", "car.Yaw", "car.Pitch", "car.Roll", "car.Suspension.NormalizedTravel.FrontLeft", "car.Suspension.NormalizedTravel.FrontRight", "car.Suspension.NormalizedTravel.RearLeft", "car.Suspension.NormalizedTravel.RearRight", "car.Tyre.SlipRatio.FrontLeft", "car.Tyre.SlipRatio.FrontRight", "car.Tyre.SlipRatio.RearLeft", "car.Tyre.SlipRatio.RearRight", "car.WheelRotationSpeed.FrontLeft", "car.WheelRotationSpeed.FrontRight", "car.WheelRotationSpeed.RearLeft", "car.WheelRotationSpeed.RearRight", "car.WheelOnRumbleStrip.FrontLeft", "car.WheelOnRumbleStrip.FrontRight", "car.WheelOnRumbleStrip.RearLeft", "car.WheelOnRumbleStrip.RearRight", "car.WheelInPuddleDepth.FrontLeft", "car.WheelInPuddleDepth.FrontRight", "car.WheelInPuddleDepth.RearLeft", "car.WheelInPuddleDepth.RearRight", "car.SurfaceRumble.FrontLeft", "car.SurfaceRumble.FrontRight", "car.SurfaceRumble.RearLeft", "car.SurfaceRumble.RearRight", "car.Tyre.SlipAngle.FrontLeft", "car.Tyre.SlipAngle.FrontRight", "car.Tyre.SlipAngle.RearLeft", "car.Tyre.SlipAngle.RearRight", "car.Tyre.SlipSpeed.FrontLeft", "car.Tyre.SlipSpeed.FrontRight", "car.Tyre.SlipSpeed.RearLeft", "car.Tyre.SlipSpeed.RearRight", "car.Suspension.Travel.FrontLeft", "car.SuspensionTravel.FrontRight", "car.Suspension.Travel.RearLeft", "car.Suspension.Travel.RearRight", None, None, "car.CarPerformanceIndex", None, "car.NumCylinders", "car.Position.X", "car.Position.Y", "car.Position.Z", "car.Speed", "car.Power", "car.Torque", "car.Tyre.Temp.FrontLeft", "car.Tyre.Temp.FrontRight", "car.Tyre.Temp.RearLeft", "car.Tyre.Temp.RearRight", "car.Boost", "car.Fuel.Level", "car.Distance", "car.Lap.Best", "car.Lap.Last", "car.Lap.Time", "car.CurrentTime", "car.LapNumber", "car.RacePosition", "car.Throttle", "car.Brake", "car.Clutch", "car.HandBrake", "car.Gear", "car.Steering", "car.NormalizedDrivingLine", "car.NormalizedAIBrakeDifference"],
    "pcars1":        ["meta.BuildVersionNumber","meta.PacketType", None, "meta.PlayerIndex","meta.NumParticipants","car.Throttle.Unfiltered","car.Brake.Unfiltered","car.Steering.Unfiltered","car.Clutch.Unfiltered","car.RaceStateFlags","car.LapsInEvent","car.Lap.Best","car.Lap.Last","car.CurrentTime","car.SplitTimeAhead","car.SplitTimeBehind","car.SplitTime","car.EventTimeRemaining","car.Lap.FastestTime.Personal","car.Lap.FastestTime.World","car.CurrentSectorTime.1","car.CurrentSectorTime.2","car.CurrentSectorTime.3","track.FastestSectorTime.Current.1","track.FastestSectorTime.Current.2","track.FastestSectorTime.Current.3","track.FastestSectorTime.Personal.1","track.FastestSectorTime.Personal.2","track.FastestSectorTime.Personal.3","track.FastestSectorTime.World.1","track.FastestSectorTime.World.2","track.FastestSectorTime.World.3","car.JoyPad","car.HighestFlag","car.PitModeSchedule","car.Oil.Temp","car.Oil.Pressure","car.Water.Temp","car.Water.Pressure","car.Fuel.Pressure",None,"car.Fuel.Capacity","car.Brake","car.Throttle","car.Clutch","car.Steering","car.Fuel.Level","car.Speed","car.Rpm.Current","car.Rpm.Max","car.Gear","car.Boost","car.EnforcedPitStopLap","car.CrashState","car.Odometer","car.Orientation.X","car.Orientation.Y","car.Orientation.Z","car.Velocity.Local.X","car.Velocity.Local.Y","car.Velocity.Local.Z","car.Velocity.World.X","car.Velocity.World.Y","car.Velocity.World.Z","car.Velocity.Angular.X","car.Velocity.Angular.Y","car.Velocity.Angular.Z","car.Acceleration.Local.X","car.Acceleration.Local.Y","car.Acceleration.Local.Z","car.Acceleration.World.X","car.Acceleration.World.Y","car.Acceleration.World.Z","car.ExtentsCentre.X","car.ExtentsCentre.Y","car.ExtentsCentre.Z","car.Tyre.Flags.FrontLeft","car.Tyre.Flags.FrontRight","car.Tyre.Flags.RearLeft","car.Tyre.Flags.RearRight","car.Terrain.FrontLeft","car.Terrain.FrontRight","car.Terrain.RearLeft","car.Terrain.RearRight","car.Tyre.Y.FrontLeft","car.Tyre.Y.FrontRight","car.Tyre.Y.RearLeft","car.Tyre.Y.RearRight","car.Tyre.RPS.FrontLeft","car.Tyre.RPS.FrontRight","car.Tyre.RPS.RearLeft","car.Tyre.RPS.RearRight","car.Tyre.SlipSpeed.FrontLeft","car.Tyre.SlipSpeed.FrontRight","car.Tyre.SlipSpeed.RearLeft","car.Tyre.SlipSpeed.RearRight","car.Tyre.Temp.FrontLeft","car.Tyre.Temp.FrontRight","car.Tyre.Temp.RearLeft","car.Tyre.Temp.RearRight","car.Tyre.Grip.FrontLeft","car.Tyre.Grip.FrontRight","car.Tyre.Grip.RearLeft","car.Tyre.Grip.RearRight","car.Tyre.HeightAboveGround.FrontLeft","car.Tyre.HeightAboveGround.FrontRight","car.Tyre.HeightAboveGround.RearLeft","car.Tyre.HeightAboveGround.RearRight","car.Tyre.LateralStiffness.FrontLeft","car.Tyre.LateralStiffness.FrontRight","car.Tyre.LateralStiffness.RearLeft","car.Tyre.LateralStiffness.RearRight","car.Tyre.Wear.FrontLeft","car.Tyre.Wear.FrontRight","car.Tyre.Wear.RearLeft","car.Tyre.Wear.RearRight","car.Brake.Damage.FrontLeft","car.Brake.Damage.FrontRight","car.Brake.Damage.RearLeft","car.Brake.Damage.RearRight","car.Suspension.Damage.FrontLeft","car.Suspension.Damage.FrontRight","car.Suspension.Damage.RearLeft","car.Suspension.Damage.RearRight","car.Brake.Temp.FrontLeft","car.Brake.Temp.FrontRight","car.Brake.Temp.RearLeft","car.Brake.Temp.RearRight","car.Tyre.TreadTemp.FrontLeft","car.Tyre.TreadTemp.FrontRight","car.Tyre.TreadTemp.RearLeft","car.Tyre.TreadTemp.RearRight","car.Tyre.LayerTemp.FrontLeft","car.Tyre.LayerTemp.FrontRight","car.Tyre.LayerTemp.RearLeft","car.Tyre.LayerTemp.RearRight","car.Tyre.CarcassTemp.FrontLeft","car.Tyre.CarcassTemp.FrontRight","car.Tyre.CarcassTemp.RearLeft","car.Tyre.CarcassTemp.RearRight","car.Tyre.RimTemp.FrontLeft","car.Tyre.RimTemp.FrontRight","car.Tyre.RimTemp.RearLeft","car.Tyre.RimTemp.RearRight","car.Tyre.InternalAirTemp.FrontLeft","car.Tyre.InternalAirTemp.FrontRight","car.Tyre.InternalAirTemp.RearLeft","car.Tyre.InternalAirTemp.RearRight","car.WheelLocalPositionY.FrontLeft","car.WheelLocalPositionY.FrontRight","car.WheelLocalPositionY.RearLeft","car.WheelLocalPositionY.RearRight","car.RideHeight.FrontLeft","car.RideHeight.FrontRight","car.RideHeight.RearLeft","car.RideHeight.RearRight","car.SuspensionTravel.FrontLeft","car.SuspensionTravel.FrontRight","car.SuspensionTravel.RearLeft","car.SuspensionTravel.RearRight","car.SuspensionVelocity.FrontLeft","car.SuspensionVelocity.FrontRight","car.SuspensionVelocity.RearLeft","car.SuspensionVelocity.RearRight","car.AirPressure.FrontLeft","car.AirPressure.FrontRight","car.AirPressure.RearLeft","car.AirPressure.RearRight","car.Engine.Speed","car.Torque","car.AeroDamage","car.Engine.Damage","weather.AmbientTemperature","weather.TrackTemperature","weather.RainDensity","weather.WindSpeed","weather.WindDirection.X","weather.WindDirection.Y","race.TrackLength","car.Wings.1","car.Wings.2","car.DPad"],
    "pcars2_tele":    pcars2_header + ["car.PlayerIndex","car.Throttle.Unfiltered","car.Brake.Unfiltered","car.Steering.Unfiltered","car.Clutch.Unfiltered",None,"car.Oil.Temp","car.Oil.Pressure","car.Water.Temp","car.Water.Pressure","car.Fuel.Pressure","car.Fuel.Capacity","car.Brake","car.Throttle","car.Clutch","car.Fuel.Level","car.Speed","car.Rpm.Current","car.Rpm.Max","car.Steering","car.Gear","car.Boost","car.CrashState","car.Odometer","car.Orientation.X","car.Orientation.Y","car.Orientation.Z","car.Velocity.Local.X","car.Velocity.Local.Y","car.Velocity.Local.Z","car.Velocity.World.X","car.Velocity.World.Y","car.Velocity.World.Z","car.Velocity.Angular.X","car.Velocity.Angular.Y","car.Velocity.Angular.Z","car.Acceleration.Local.X","car.Acceleration.Local.Y","car.Acceleration.Local.Z","car.Acceleration.World.X","car.Acceleration.World.Y","car.Acceleration.World.Z","car.ExtentsCentre.X","car.ExtentsCentre.Y","car.ExtentsCentre.Z","car.Tyre.Flags.FrontLeft","car.Tyre.Flags.FrontRight","car.Tyre.Flags.RearLeft","car.Tyre.Flags.RearRight","car.Terrain.FrontLeft","car.Terrain.FrontRight","car.Terrain.RearLeft","car.Terrain.RearRight","car.Tyre.Y.FrontLeft","car.Tyre.Y.FrontRight","car.Tyre.Y.RearLeft","car.Tyre.Y.RearRight","car.Tyre.RPS.FrontLeft","car.Tyre.RPS.FrontRight","car.Tyre.RPS.RearLeft","car.Tyre.RPS.RearRight","car.Tyre.Temp.FrontLeft","car.Tyre.Temp.FrontRight","car.Tyre.Temp.RearLeft","car.Tyre.Temp.RearRight","car.Tyre.HeightAboveGround.FrontLeft","car.Tyre.HeightAboveGround.FrontRight","car.Tyre.HeightAboveGround.RearLeft","car.Tyre.HeightAboveGround.RearRight","car.Tyre.Wear.FrontLeft","car.Tyre.Wear.FrontRight","car.Tyre.Wear.RearLeft","car.Tyre.Wear.RearRight","car.Brake.Damage.FrontLeft","car.Brake.Damage.FrontRight","car.Brake.Damage.RearLeft","car.Brake.Damage.RearRight","car.Suspension.Damage.FrontLeft","car.Suspension.Damage.FrontRight","car.Suspension.Damage.RearLeft","car.Suspension.Damage.RearRight","car.Brake.Temp.FrontLeft","car.Brake.Temp.FrontRight","car.Brake.Temp.RearLeft","car.Brake.Temp.RearRight","car.Tyre.TreadTemp.FrontLeft","car.Tyre.TreadTemp.FrontRight","car.Tyre.TreadTemp.RearLeft","car.Tyre.TreadTemp.RearRight","car.Tyre.LayerTemp.FrontLeft","car.Tyre.LayerTemp.FrontRight","car.Tyre.LayerTemp.RearLeft","car.Tyre.LayerTemp.RearRight","car.CarcassTemp.FrontLeft","car.CarcassTemp.FrontRight","car.CarcassTemp.RearLeft","car.CarcassTemp.RearRight","car.Tyre.RimTemp.FrontLeft","car.Tyre.RimTemp.FrontRight","car.Tyre.RimTemp.RearLeft","car.Tyre.RimTemp.RearRight","car.Tyre.InternalAirTemp.FrontLeft","car.Tyre.InternalAirTemp.FrontRight","car.Tyre.InternalAirTemp.RearLeft","car.Tyre.InternalAirTemp.RearRight","car.Tyre.TempLeft.FrontLeft","car.Tyre.TempLeft.FrontRight","car.Tyre.TempLeft.RearLeft","car.Tyre.TempLeft.RearRight","car.Tyre.TempCenter.FrontLeft","car.Tyre.TempCenter.FrontRight","car.Tyre.TempCenter.RearLeft","car.Tyre.TempCenter.RearRight","car.Tyre.TempRight.FrontLeft","car.Tyre.TempRight.FrontRight","car.Tyre.TempRight.RearLeft","car.Tyre.TempRight.RearRight","car.WheelLocalPositionY.FrontLeft","car.WheelLocalPositionY.FrontRight","car.WheelLocalPositionY.RearLeft","car.WheelLocalPositionY.RearRight","car.RideHeight.FrontLeft","car.RideHeight.FrontRight","car.RideHeight.RearLeft","car.RideHeight.RearRight","car.Suspension.Travel.FrontLeft","car.Suspension.Travel.FrontRight","car.Suspension.Travel.RearLeft","car.Suspension.Travel.RearRight","car.Suspension.Velocity.FrontLeft","car.Suspension.Velocity.FrontRight","car.Suspension.Velocity.RearLeft","car.Suspension.Velocity.RearRight","car.Suspension.RideHeight.FrontLeft","car.Suspension.RideHeight.FrontRight","car.Suspension.RideHeight.RearLeft","car.Suspension.RideHeight.RearRight","car.AirPressure.FrontLeft","car.AirPressure.FrontRight","car.AirPressure.RearLeft","car.AirPressure.RearRight","car.Engine.Speed","car.Torque","car.Wings.1","car.Wings.2","car.HandBrake","car.AeroDamage","car.Engine.Damage","car.JoyPad","car.DPad","car.TurboBoostPressure","car.Position.X","car.Position.Y","car.Position.Z","car.Brake.Bias","car.TickCount"],
    "pcars2_state":   pcars2_header + ["state.BuildVersionNumber",None] + pcars2_weather,
    "pcars2_weather": pcars2_header + pcars2_weather,
    "f1_2019_motion": f1_2019_header + ["car.Position.X","car.Position.Y","car.Position.Z","car.Velocity.World.X","car.Velocity.World.Y","car.Velocity.World.Z","car.worldForwardDir.X","car.worldForwardDir.Y","car.worldForwardDir.Z","car.worldRightDir.X","car.worldRightDir.Y","car.worldRightDir.Z","car.gForce.Lateral","car.gForce.Longitudinal","car.gForce.Vertical","car.yaw","car.pitch","car.roll","car.Suspension.Position.FrontLeft","car.Suspension.Position.FrontRight","car.Suspension.Position.RearLeft","car.Suspension.Position.FrontLeft","","car.Suspension.Velocity.FrontLeft","car.Suspension.Velocity.FrontRight","car.Suspension.Velocity.RearLeft","car.Suspension.Velocity.FrontLeft","","car.Suspension.Acceleration.FrontLeft","car.Suspension.Acceleration.FrontRight","car.Suspension.Acceleration.RearLeft","car.Suspension.Acceleration.FrontLeft","","car.Wheel.Speed.FrontLeft","car.Wheel.Speed.FrontRight","car.Wheel.Speed.RearLeft","car.Wheel.Speed.FrontLeft","","car.Wheel.Slip.FrontLeft","car.Wheel.Slip.FrontRight","car.Wheel.Slip.RearLeft","car.Wheel.Slip.FrontLeft","","car.Velocity.Local.X","car.Velocity.Local.Y","car.Velocity.Local.Z","car.Velocity.Angular.X","car.Velocity.Angular.Y","car.Velocity.Angular.Z","car.Acceleration.Local.X","car.Acceleration.Local.Y","car.Acceleration.Local.Z","car.frontWheelsAngle"],
    "f1":             ["meta.Timestamp","car.Lap.Time","car.Lap.Distance","car.Distance","car.Position.X","car.Position.Y","car.Position.Z","car.Speed","car.Velocity.World.X","car.Velocity.World.Y","car.Velocity.World.Z","car.Roll.X","car.Roll.Y","car.Roll.Z","car.Pitch.X","car.Pitch.Y","car.Pitch.Z","car.Suspension.Position.RearLeft","car.Suspension.Position.RearRight","car.Suspension.Position.FrontLeft","car.Suspension.Position.FrontRight","car.Suspension.Velocity.RearLeft","car.Suspension.Velocity.RearRight","car.Suspension.Velocity.FrontLeft","car.Suspension.Velocity.RearRight","car.Wheel.Velocity.BlackLeft","car.Wheel.Velocity.BackRight","car.Wheel.Velocity.FrontLeft","car.Wheel.Velocity.FrontRight","car.Throttle","car.Steering","car.Brake","car.Clutch","car.Gear","car.GForce.Lateral","car.GForce.Longitudinal","car.Lap","car.Rpm.Current",None,"car.RacePosition","car.Kers.Current","car.Kers.Max",None,None,None,None,None,None,None,None,None,None,None,None,None,None,None,None,None,None,None,None,None,None],
    "dirt":           ["meta.Timestamp","car.Lap.Time","car.Lap.Distance","car.Distance","car.Position.X","car.Position.Y","car.Position.Z","car.Speed","car.Velocity.World.X","car.Velocity.World.Y","car.Velocity.World.Z","car.Roll.X","car.Roll.Y","car.Roll.Z","car.Pitch.X","car.Pitch.Y","car.Pitch.Z","car.Suspension.Position.RearLeft","car.Suspension.Position.RearRight","car.Suspension.Position.FrontLeft","car.Suspension.Position.FrontRight","car.Suspension.Velocity.RearLeft","car.Suspension.Velocity.RearRight","car.Suspension.Velocity.FrontLeft","car.Suspension.Velocity.RearRight","car.Wheel.Velocity.BlackLeft","car.Wheel.Velocity.BackRight","car.Wheel.Velocity.FrontLeft","car.Wheel.Velocity.FrontRight","car.Throttle","car.Steering","car.Brake","car.Clutch","car.Gear","car.GForce.Lateral","car.GForce.Longitudinal","car.Lap","car.Rpm.Current",None,"car.RacePosition"]
}

enums = {
    "onoff": ["ON","OFF"],
    "forza_state.Game": ["Menu","Playing"],
    "pcars_state.Game": ["Exited","Main Menu","Playing","Paused","Menu","Restarting","Replay","Main Menu Replay"],
    "pcars_state.Session": ["Invalid","Practice","Test","Qualify","Formation Lap","Race","Time Attack"],
    "pcars_state.Race": ["Invalid","Not Started","Racing","Finished","Disqualified","Retired","DNF"],
    "pcars_car.Terrain": ["ROAD","LOW GRIP ROAD","BUMPY ROAD1","BUMPY ROAD2","BUMPY ROAD3","MARBLES","GRASSY BERMS","GRASS","GRAVEL","BUMPY GRAVEL","RUMBLE STRIPS","DRAINS","TYREWALLS","CEMENTWALLS","GUARDRAILS","SAND","BUMPY SAND","DIRT","BUMPY DIRT","DIRT ROAD","BUMPY DIRT ROAD","PAVEMENT","DIRT BANK","WOOD","DRY VERGE","EXIT RUMBLE STRIPS","GRASSCRETE","LONG GRASS","SLOPE GRASS","COBBLES","SAND ROAD","BAKED CLAY","ASTROTURF","SNOWHALF","SNOWFULL"],
    "forza_car.DriveTrain": ["FWD","RWD","AWD"],
    "forza_car.Class": ["D","C","B","A","S1","S2","S3","X"]
}


def validate_conf(config, key):
    if key not in config:
        raise Exception("Invalid configuration received from Splunk: key '%s' is missing." % key)

# Routine to get the value of an input
def get_config():
    config = {}

    try:
        # read everything from stdin
        config_str = sys.stdin.read()

        # parse the config XML
        doc = xml.dom.minidom.parseString(config_str)
        root = doc.documentElement
        conf_node = root.getElementsByTagName("configuration")[0]
        if conf_node:
            logging.debug("XML: found configuration")
            stanza = conf_node.getElementsByTagName("stanza")[0]
            if stanza:
                stanza_name = stanza.getAttribute("name")
                if stanza_name:
                    logging.debug("XML: found stanza " + stanza_name)
                    config["name"] = stanza_name

                    params = stanza.getElementsByTagName("param")
                    for param in params:
                        param_name = param.getAttribute("name")
                        logging.debug("XML: found param '%s'" % param_name)
                        if param_name and param.firstChild and \
                           param.firstChild.nodeType == param.firstChild.TEXT_NODE:
                            data = param.firstChild.data
                            config[param_name] = data
                            logging.debug("XML: '%s' -> '%s'" % (param_name, data))

        checkpnt_node = root.getElementsByTagName("checkpoint_dir")[0]
        if checkpnt_node and checkpnt_node.firstChild and \
           checkpnt_node.firstChild.nodeType == checkpnt_node.firstChild.TEXT_NODE:
            config["checkpoint_dir"] = checkpnt_node.firstChild.data

        if not config:
            raise Exception("Invalid configuration received from Splunk.")

        # just some validation: make sure these keys are present (required)
        validate_conf(config, "name")
        validate_conf(config, "ratelimit")
        validate_conf(config, "port")
        validate_conf(config, "bindip")
        validate_conf(config, "multimetric")
    except Exception as e:
        raise Exception("Error getting Splunk configuration via STDIN: %s" % str(e))

    return config

# Routine to index data
def run_script(): 

    # Get Configs
    config=get_config()

    opt_multimetric=(config["multimetric"]=="True" or config["multimetric"]=="1")
    opt_filtermenu=(config["filtermenu"]=="True" or config["filtermenu"]=="1")
    opt_ip=config["bindip"]
    opt_port=int(config["port"])
    opt_rate_limit=float(config["ratelimit"])/1000
    opt_whitelist=config["whitelist"]

    # Prebuild whitelist to improve performance
    whitelist = {}
    for label in labels:
        arr = map(lambda metric: metric is not None and bool(re.search(opt_whitelist,metric)),labels[label])
        count = sum(arr)
        if count>0:
            whitelist[label] = arr
            logging.info("Whitelisted {}/{} metrics in {}".format(count,len(labels[label]),label))
        else:
            whitelist[label] = None
            logging.info("Whitelisted {}/{} metrics in {}, disabling".format(count,len(labels[label]),label))
        
    
    # Start listening
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((opt_ip,opt_port))
    logging.info("Listening on {}:{} with rate limit of {}s in {} metric mode".format(opt_ip,opt_port,opt_rate_limit,["single","multi"][opt_multimetric]))
    
    
    cars = {}
    times = {}
    strings = {}
    dimensions = {}
    drops = {}
    limiter = {}

    def list_get (l, idx, default):
        try:
            return l[idx]
        except IndexError:
            return default

    def ratelimit(time,i,host,limit):
        key = "{}:{}".format(i,host)
        if time >= limiter.get(key,0)+limit:
            limiter[key] = time
            return True
        else:
            drops[host]+=1
            #rops[host] = drops.get(host,0) + 1
            #dimensions[host]['metric_name:net.DroppedEvents']+=1 # It should be logically impossible for this to not exist
            #dimensions[host]['metric_name:net.DroppedEvents'] = dimensions[host].get('metric_name:net.DroppedEvents',0)+1
            return False

    while True:
        try:
            packet, addr = sock.recvfrom(1500)
            now = time.time()
            host = addr[0]
            source = None

            if not dimensions.has_key(host):
                dimensions[host] = {"GameState": "Unknown"}
                drops[host] = 0

            size = len(packet)

            logging.debug("Received {} bytes from {}".format(size,host))

            #Check for static sized payloads
            if(size == 324): #Forza Horizon 4
                #if whitelist["forza"] and now >= (limiter.get("324:"+host,0)+opt_rate_limit):
                if whitelist["forza"] and ratelimit(now,"324",host,opt_rate_limit):
                    values = struct.unpack('<i I 27f 4i 20f 5i 12x 17f H 6B 3b x',packet)
                    if(opt_filtermenu and values[0] == 0): continue # In Menu, no useful data

                    limiter["324:"+host] = now
                    source = "Forza Horizon 4"
                    label = "forza"

                    dimensions[host]['GameState'] = enums["forza_state.Game"][values[0]]
                    dimensions[host]['CarName'] = forza_cars.get(values[53],"Unknown Car {}".format(values[53]))
                    dimensions[host]['CarClass'] = list_get(enums["forza_car.Class"],values[54],values[54])
                    dimensions[host]['CarDriveTrain'] = list_get(enums["forza_car.DriveTrain"],values[56],values[56])

                    

            elif (size == 311): #Forza Motorsport 7 - Dash mode
                if whitelist["forza"] and now >= (limiter.get("311:"+host,0)+opt_rate_limit):
                    values = struct.unpack('<i I 27f 4i 20f 5i 17f H 6B 3b',packet)
                    if(opt_filtermenu and values[0] == 0): continue # In Menu, no useful data
                    
                    limiter["311:"+host] = now
                    source = "Forza Motorsport 7"
                    label = "forza"
                    
                    dimensions[host]['GameState'] = enums["forza_state.Game"][values[0]]
                    dimensions[host]['CarName'] = forza_cars.get(values[53],"Unknown Car {}".format(values[53]))
                    dimensions[host]['CarClass'] = list_get(enums["forza_car.Class"],values[54],values[54])
                    dimensions[host]['CarDriveTrain'] = list_get(enums["forza_car.DriveTrain"],values[56],values[56])

            elif (size == 232): #Forza Motorsport 7 - Sled mode
                if whitelist["forza"] and now >= (limiter.get("232:"+host,0)+opt_rate_limit):
                    values = struct.unpack('<i I 27f 4i 20f 5i',packet)
                    if(opt_filtermenu and values[0] == 0): continue # In Menu, no useful data
                    
                    limiter["232:"+host] = now
                    source = "Forza Motorsport 7"
                    label = "forza"
                    
                    dimensions[host]['GameState'] = enums["forza_state.Game"][values[0]]
                    dimensions[host]['CarName'] = forza_cars.get(values[53],"Unknown Car {}".format(values[53]))
                    dimensions[host]['CarClass'] = list_get(enums["forza_car.Class"],values[54],values[54])
                    dimensions[host]['CarDriveTrain'] = list_get(enums["forza_car.DriveTrain"],values[56],values[56])

            elif (size == 559): #Project Cars 2 Patch 5 - Telemetry
                if whitelist["pcars2_tele"] and now >= (limiter.get("559:"+host,0)+opt_rate_limit):
                    if(opt_filtermenu and not dimensions[host]['GameState'] == "Playing"): continue # In Menu, no useful data

                    values = struct.unpack('<2I 4B bBBbBBhHhHHBBBBffHHbBBB 22f 8B 8f 4B 4f 12B 4h 32H 16f 8H ff 5B IB 160x 4f BI',packet)

                    #Fix Gears Nibble
                    values[45] = values[45] % 16
                    if(values[45] == 15): values[45] = -1 # Reverse

                    limiter["559:"+host] = now
                    source = "Project Cars 2"
                    label = "pcars2_tele"
                    

                    cns = cars.get(host,[])
                    idx = values[6]*2 # Move to correct offset
                    if idx<len(cns):
                        dimensions[host]['CarName'] = str(format(cns[idx]))

            elif (size == 1063): #Project Cars 2 Patch 5 - Timing Data
                continue      
            elif (size == 24): #Project Cars 2 Patch 5 - Game State (Dimensions Only)
                #if whitelist["pcars2_state"] and now >= (limiter.get("24:"+host,0)+opt_rate_limit):
                    #limiter["24:"+host] = now
                    #source = "Project Cars 2"
                    #label = "pcars2_state"
                values = struct.unpack('<2I 4B HbbbBBbbbxx',packet)

                dimensions[host]['GameState'] = enums["pcars_state.Game"][values[7] % 8]
                dimensions[host]['SessionState'] = enums["pcars_state.Session"][values[7]>>4 % 8]

                dimensions[host]['CarHeadlights'] = enums["onoff"][values[11]&1]
                dimensions[host]['CarEngine'] = enums["onoff"][values[11]&2]
                dimensions[host]['CarEngineWarning'] = enums["onoff"][values[11]&4]
                dimensions[host]['CarSpeedLimiter'] = enums["onoff"][values[11]&8]
                dimensions[host]['CarABS'] = enums["onoff"][values[11]&16]
                dimensions[host]['CarHandBrake'] = enums["onoff"][values[11]&32]

            elif (size == 1164): #Project Cars 2 Patch 5 - Vehicle Names
                #carsnames[host] = struct.unpack('<12x HI64sxx HI64sxx HI64sxx HI64sxx HI64sxx HI64sxx HI64sxx HI64sxx HI64sxx HI64sxx HI64sxx HI64sxx HI64sxx HI64sxx HI64sxx HI64sxx',packet)
                #strings["pcars2:"+host] = struct.unpack('<12x 4xI64s 4xI64s 4xI64s 4xI64s 4xI64s 4xI64s 4xI64s 4xI64s 4xI64s 4xI64s 4xI64s 4xI64s 4xI64s 4xI64s 4xI64s 4xI64s',packet)
                cars[host] = struct.unpack('<12x 8x64s 8x64s 8x64s 8x64s 8x64s 8x64s 8x64s 8x64s 8x64s 8x64s 8x64s 8x64s 8x64s 8x64s 8x64s 8x64s',packet)
                times[host] = now

            #elif (size == 1452): #Project Cars 2 Patch 5 - Class Names (Wasnt comprehensive, so useless in the end)
            #    a = struct.unpack('<12x I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s I20s',packet)
            #    cars[host] = [None] * 16
            #    b = {}
            #    for x in range(60): # Build dict of ClassID -> ClassName
            #        b[a[x*2]] = a[x*2+1]
            #    logging.info(b)
            #    for c in range(16): # Replace ID with String
            #        cars[host][c] = {"car.class": b[strings["pcars2:"+host][c*2]].rstrip('\x00'), "car.name": strings["pcars2:"+host][c*2+1].rstrip('\x00')} #need to move this to a new output array
            #    logging.info(cars[host])
            #    strings["pcars2:"+host] = None
            #elif (size == 374): #Project Cars 1 - Telemetry
            #    if whitelist["pcars2_tele"] and now >= (limiter.get("374:"+host,0)+opt_rate_limit):
            #        limiter["374:"+host] = now
            #        source = "Project Cars 1"
            #        label = "pcars2_tele"
            #        values = struct.unpack('<2I 4B bBBbBBhHhHHBBBBffHHbBBB 22f 8B 8f 4B 4f 12B 4h 32H 16f 8H ff 5B IB',packet)
            #elif (size == 16): #Project Cars 1 - Game State
            #    if whitelist["pcars2_state"] and now >= (limiter.get("16:"+host,0)+opt_rate_limit):
            #        limiter["16:"+host] = now
            #        source = "Project Cars 1"
            #        label = "pcars2_state"
            #        values = struct.unpack('<2I 4B Hc',packet)
            #elif (size == 19): #Project Cars 1 - Weather
            #    if whitelist["pcars2_weather"] and now >= (limiter.get("19:"+host,0)+opt_rate_limit):
            #        limiter["19:"+host] = now
            #        source = "Project Cars 1"
            #        label = "pcars2_weather"
            #        values = struct.unpack('<2I 4B bbBBbbb',packet)
            elif (size == 1367): #Project Cars 1 - Telemetry
                if whitelist["pcars1"] and now >= (limiter.get("1367:"+host,0)+opt_rate_limit):
                    values = struct.unpack("<HB b bb BBbBB B 21f H B B hHhHH BBBBBb ffHHBBbB 22f 8B 12f 8B 8f 12B 4h 20H 16f 4H ff BB bbBbbb 896x fBB x",packet)
                    if(opt_filtermenu and (values[7] % 8) != 2): continue # In Menu, no useful data

                    limiter["1367:"+host] = now
                    source = "Project Cars 1"
                    label = "pcars1"
                    
                    dimensions[host]['GameState'] = enums["pcars_state.Game"][values[2] % 8]
                    dimensions[host]['SessionState'] = enums["pcars_state.Session"][values[2]>>4 % 8]

                    dimensions[host]['CarHeadlight'] = enums["onoff"][values[40]&1]
                    dimensions[host]['CarEngine'] = enums["onoff"][values[40]&2]
                    dimensions[host]['CarEngineWarning'] = enums["onoff"][values[40]&4]
                    dimensions[host]['CarSpeedLimiter'] = enums["onoff"][values[40]&8]
                    dimensions[host]['CarABS'] = enums["onoff"][values[40]&16]
                    dimensions[host]['CarHandBrake'] = enums["onoff"][values[40]&32]
            
            elif (size == 1347): #Project Cars 1 - Participant Strings
                strings = struct.unpack("<3x 64s 64s 64s 64s 1088x",packet)
                dimensions[host]['CarName'] = str(strings[0])
                dimensions[host]['CarClass'] = str(strings[1])
                dimensions[host]['TrackName'] = str(strings[2])
                dimensions[host]['TrackVarient'] = str(strings[3])
                    
            elif (size == 1343): #F1 2019 - Motion
                if whitelist["f12019_motion"] and now >= (limiter.get("1343:"+host,0)+opt_rate_limit):
                    limiter["1343:"+host] = now
                    source = "F1 2019"
                    label = "f12019_motion"
                    playerindex = packet[22]
                    values = struct.unpack("<H 4B QfIB {} 6f 6h 6f {} 30f".format(playerindex*"60x",(18-playerindex)*"60x"),packet) # Removes all other cars except the players
            elif (size == 68): #Dirt Rally - Mode 0
                if whitelist["dirt"] and now >= (limiter.get("68:"+host,0)+opt_rate_limit):
                    values = struct.unpack("<17f",packet)

                    limiter["68:"+host] = now
                    source = "Codemasters"
                    label = "dirt"
                    
            elif (size == 152): #Dirt Rally - Mode 1
                if whitelist["dirt"] and now >= (limiter.get("152:"+host,0)+opt_rate_limit):
                    values = struct.unpack("<38f",packet)

                    limiter["152:"+host] = now
                    source = "Codemasters"
                    label = "dirt"
                    
            else: #Unrecognised UDP packet length
                logging.info("Unknown Packet Size '%s'" % size)
                continue 

            if source:
                data = dimensions[host].copy()
                if(opt_multimetric):
                    for enabled,name,value in zip(whitelist[label],labels[label],values):
                        if(enabled):
                            data["metric_name:{}".format(name)] = value
                    
                    data["metric_name:net.DroppedEvents"] = drops[host] # Add special DroppedEvents metric
                    print("<stream><event><time>{}</time><host>{}</host><source>{}</source><data>{}</data></event></stream>".format(now,host,source,json.dumps(data)))
                else:
                    print("<stream>")
                    for enabled,name,value in zip(whitelist[label],labels[label],values):
                        if(enabled):
                            data["metric_name"] = name
                            data["_value"] = value
                            print("<event><time>{}</time><host>{}</host><source>{}</source><data>{}</data></event>".format(now,host,source,json.dumps(data)))
                    # Add special DroppedEvents metric
                    data["metric_name"] = "net.DroppedEvents"
                    data["_value"] = drops[host]
                    print("<event><time>{}</time><host>{}</host><source>{}</source><data>{}</data></event>".format(now,host,source,json.drumps(data)))
                    print("</stream>")
                drops[host] = 0

            values = None
        except Exception as e:
            logging.error(e)
            logging.error(traceback.format_exc())

# Script must implement these args: scheme, validate-arguments
if __name__ == '__main__':
    if len(sys.argv) > 1:
        if sys.argv[1] == "--scheme":
            print(SCHEME)
        elif sys.argv[1] == "--validate-arguments":
            pass
        else:
            pass
    else:
        run_script()

    sys.exit(0)
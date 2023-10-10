#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################
# GlennNZ
# https://www.indigodomo.com

try:
    import indigo
except:
    pass

import asyncio
import threading
import subprocess
import os
import sys
import time
import logging
import traceback
from os import path

import asyncio
import aioesphomeapi
from aioesphomeapi import (
    APIClient,
    APIConnectionError,
    DeviceInfo,
    InvalidAuthAPIError,
    InvalidEncryptionKeyAPIError,
    RequiresEncryptionAPIError,
    ResolveAPIError,
)
try:
    import pydevd_pycharm
    pydevd_pycharm.settrace('localhost', port=5678, stdoutToServer=True, stderrToServer=True, suspend=False)
except:
    pass

# Note the "indigo" module is automatically imported and made available inside
# our global name space by the host process.
###############################################################################
# New Indigo Log Handler - display more useful info when debug logging
# update to python3 changes
################################################################################
class IndigoLogHandler(logging.Handler):
    def __init__(self, display_name, level=logging.NOTSET):
        super().__init__(level)
        self.displayName = display_name

    def emit(self, record):
        """ not used by this class; must be called independently by indigo """
        logmessage = ""
        try:
            levelno = int(record.levelno)
            is_error = False
            is_exception = False
            if self.level <= levelno:  ## should display this..
                if record.exc_info !=None:
                    is_exception = True
                if levelno == 5:	# 5
                    logmessage = '({}:{}:{}): {}'.format(path.basename(record.pathname), record.funcName, record.lineno, record.getMessage())
                elif levelno == logging.DEBUG:	# 10
                    logmessage = '({}:{}:{}): {}'.format(path.basename(record.pathname), record.funcName, record.lineno, record.getMessage())
                elif levelno == logging.INFO:		# 20
                    logmessage = record.getMessage()
                elif levelno == logging.WARNING:	# 30
                    logmessage = record.getMessage()
                elif levelno == logging.ERROR:		# 40
                    logmessage = '({}: Function: {}  line: {}):    Error :  Message : {}'.format(path.basename(record.pathname), record.funcName, record.lineno, record.getMessage())
                    is_error = True
                if is_exception:
                    logmessage = '({}: Function: {}  line: {}):    Exception :  Message : {}'.format(path.basename(record.pathname), record.funcName, record.lineno, record.getMessage())
                    indigo.server.log(message=logmessage, type=self.displayName, isError=is_error, level=levelno)
                    if record.exc_info !=None:
                        etype,value,tb = record.exc_info
                        tb_string = "".join(traceback.format_tb(tb))
                        indigo.server.log(f"Traceback:\n{tb_string}", type=self.displayName, isError=is_error, level=levelno)
                        indigo.server.log(f"Error in plugin execution:\n\n{traceback.format_exc(30)}", type=self.displayName, isError=is_error, level=levelno)
                    indigo.server.log(f"\nExc_info: {record.exc_info} \nExc_Text: {record.exc_text} \nStack_info: {record.stack_info}",type=self.displayName, isError=is_error, level=levelno)
                    return
                indigo.server.log(message=logmessage, type=self.displayName, isError=is_error, level=levelno)
        except Exception as ex:
            indigo.server.log(f"Error in Logging: {ex}",type=self.displayName, isError=is_error, level=levelno)

class ESPHome4Indigo:
    def __init__(self, plugin, loop, deviceid, host, port, password, devicename):
        try:
            self.plugin = plugin
            self.plugin.logger.debug("Within init of ESP Home4Indigo")
            self.deviceid = deviceid
            self.host = host
            self.port = port
            self.password = password
            self.loop = loop
            self.devicename = devicename
            self.cli = APIClient(
                self.host,
                self.port,
                self.password,
                client_info=f"Indigo {devicename}" )
            self._killConnection = False
            #.create_task(self.loop_esphome(cli=self.cli, deviceid=self.deviceid) )
            self._task = self.loop.create_task( self.loop_esphome(cli=self.cli, deviceid=self.deviceid) )
            self.plugin.logger.debug("End of init ESP Home4Indigo")
        except:
            self.plugin.logger.exception("Exception")

    def switch_command(self, key, state):
        try:
            self.loop.create_task(self.cli.switch_command(key, state))
        except:
            self.logger.exception("Exception")

    def change_callback(self,state):
        """Print the state changes of the device.."""
        try:
            if self.plugin.debug2:
                self.plugin.logger.debug(state)

            key = state.key
            state = state.state

            for device in indigo.devices.iter("self"):
                if device.deviceTypeId =="ESPsensor":
                    if str(device.states['key'])== str(key):
                        if self.plugin.debug2:
                            self.plugin.logger.debug(f"Matching device {device.name} to received state {state} found.  Updating")
                        device.updateStateOnServer(key="sensorValue", value=state, uiValue=str(state)+device.states['units'])
                if device.deviceTypeId =="ESPswitchType":
                    if str(device.states['key'])== str(key):
                        if self.plugin.debug2:
                            self.plugin.logger.debug(f"Matching device {device.name} to received state {state} found.  Updating")
                        device.updateStateOnServer(key="onOffState", value=state)

        except:
            self.plugin.logger.exception(f"Exception in subscription callback")


    async def updateDeviceInfo(self, mainESPCoredevice, device_info, api_version):
        self.plugin.logger.debug(f"Updating Core device information states {mainESPCoredevice.name}")
        updatedStates = [
            {'key': 'deviceIsOnline', 'value': True},
            {'key': 'deviceStatus', 'value': "Connected"},
            {'key': 'uses_password', 'value': device_info.uses_password},
            {'key': 'name', 'value': device_info.name },
            {'key': 'mac_address', 'value': device_info.mac_address},
            {'key': 'api_version', 'value': f"{api_version.major}.{api_version.minor}" },
            {'key': 'model', 'value': device_info.model},
            {'key': 'manufacturer', 'value': device_info.manufacturer},
            {'key': 'esphome_version', 'value': device_info.esphome_version},
            {'key': 'web_server_port', 'value': device_info.webserver_port},
            {'key': 'friendly_name', 'value': device_info.friendly_name}
        ]
        mainESPCoredevice.updateStatesOnServer(updatedStates)
        mainESPCoredevice.updateStateImageOnServer(indigo.kStateImageSel.PowerOn)
        self.enable_linked()


    async def setupDevices(self, mainESPCoredevice, device_info, entities, services, api_version):
        self.plugin.logger.info(f"Creating child devices for {mainESPCoredevice.name}")
        await self.updateDeviceInfo(mainESPCoredevice, device_info, api_version)

        ## Read Props of Main device and set hidden deviceSetup to True - removing the Blue Messaging, until recreate Button pressed again
        props = mainESPCoredevice.pluginProps
        self.plugin.logger.debug(f"{props}")
        props["deviceSetup"] = True
        mainESPCoredevice.replacePluginPropsOnServer(indigo.Dict(props))

        try:
            newstates = []
            x = 1
            props_dict = dict()
            props_dict["member_of_device_group"] = True
            props_dict["linkedPrimaryIndigoDevice"] = mainESPCoredevice.name
            props_dict["linkedPrimaryIndigoDeviceId"] = mainESPCoredevice.id

            for entity in entities:
                self.plugin.logger.debug(f"{entity} ")
                if x== 1:
                    if type(entity) == aioesphomeapi.model.SensorInfo:
                        props_dict["SupportsSensorValue"] = True
                        props_dict["SupportsOnState"] = True
                        props_dict["device_number"] = x - 1
                        newdevice = indigo.device.create(indigo.kProtocol.Plugin,
                                                       deviceTypeId="ESPsensor",
                                                       address=mainESPCoredevice.address,
                                                       #groupWithDevice=int(mainESPCoredevice.id), ## Don't group first device Leave core seperate
                                                       name=mainESPCoredevice.name+"-"+entity.name,
                                                       folder=mainESPCoredevice.folderId,
                                                       description=mainESPCoredevice.name + "-Sensor",
                                                       props=props_dict )
                        stateList =  [
                            {'key': 'deviceIsOnline', 'value': True},
                            {'key': 'deviceStatus', 'value': "Connected"},
                            {'key': 'key', 'value': entity.key},
                            {'key': 'units', 'value': entity.unit_of_measurement},
                            {'key': 'name', 'value': entity.name},
                        ]
                        asyncio.sleep(3)
                        newdevice.updateStatesOnServer(stateList)
                        x=x+1
                    ## Switch
                    elif type(entity) == aioesphomeapi.model.SwitchInfo:
                        props_dict["SupportsStatusRequest"] = True
                        props_dict["SupportsOnState"] = True
                        # self.plugin.logger.info(f"{entity}")
                        props_dict["device_number"] = x - 1
                        newdevice = indigo.device.create(indigo.kProtocol.Plugin,
                                                         deviceTypeId="ESPswitchType",
                                                         address=mainESPCoredevice.address,
                                                         # groupWithDevice=int(mainESPCoredevice.id), ## Don't group first device Leave core seperate
                                                         name=mainESPCoredevice.name + "-" + entity.name,
                                                         folder=mainESPCoredevice.folderId,
                                                         description=mainESPCoredevice.name + "-Switch",
                                                         props=props_dict)
                        stateList = [
                            {'key': 'deviceIsOnline', 'value': True},
                            {'key': 'deviceStatus', 'value': "Connected"},
                            {'key': 'key', 'value': entity.key},
                            {'key': 'onOffState', 'value': entity.assumed_state},
                            {'key': 'name', 'value': entity.name},
                        ]
                        asyncio.sleep(3)
                        newdevice.updateStatesOnServer(stateList)
                        x=x+1
                else:
                    first_device_id = newdevice.id
                    if type(entity) == aioesphomeapi.model.SensorInfo:
                        props_dict["SupportsSensorValue"] = True
                        props_dict["SupportsOnState"] = True
                        self.plugin.logger.info(f"{entity}")
                        props_dict["device_number"] = x - 1
                        newdevice = indigo.device.create(indigo.kProtocol.Plugin,
                                                       deviceTypeId="ESPsensor",
                                                       address=mainESPCoredevice.address,
                                                       groupWithDevice=int(first_device_id),
                                                       name=mainESPCoredevice.name+"-"+entity.name,
                                                       folder=mainESPCoredevice.folderId,
                                                       description=mainESPCoredevice.name + "-Sensor",
                                                       props=props_dict )
                        stateList =  [
                            {'key': 'deviceIsOnline', 'value': True},
                            {'key': 'deviceStatus', 'value': "Connected"},
                            {'key': 'key', 'value': entity.key},
                            {'key': 'units', 'value': entity.unit_of_measurement},
                            {'key': 'name', 'value': entity.name},
                        ]
                        asyncio.sleep(3)
                        newdevice.updateStatesOnServer(stateList)
                        x=x+1

                    elif type(entity) == aioesphomeapi.model.SwitchInfo:
                        props_dict["SupportsStatusRequest"] = True
                        props_dict["SupportsOnState"] = True
                        # self.plugin.logger.info(f"{entity}")
                        props_dict["device_number"] = x - 1
                        newdevice = indigo.device.create(indigo.kProtocol.Plugin,
                                                         deviceTypeId="ESPswitchType",
                                                         address=mainESPCoredevice.address,
                                                         groupWithDevice=int(first_device_id),## Don't group first device Leave core seperate
                                                         name=mainESPCoredevice.name + "-" + entity.name,
                                                         folder=mainESPCoredevice.folderId,
                                                         description=mainESPCoredevice.name + "-Switch",
                                                         props=props_dict)
                        stateList = [
                            {'key': 'deviceIsOnline', 'value': True},
                            {'key': 'deviceStatus', 'value': "Connected"},
                            {'key': 'key', 'value': entity.key},
                            {'key': 'onOffState', 'value': entity.assumed_state},
                            {'key': 'name', 'value': entity.name},
                        ]
                        asyncio.sleep(3)
                        newdevice.updateStatesOnServer(stateList)
                        x=x+1

            dev_id_list = indigo.device.getGroupList(mainESPCoredevice)
            self.plugin.logger.debug(dev_id_list)

        except:
            self.plugin.logger.exception("")
            return

    def disconnect(self):
        """Disconnect from device."""
        self.plugin.logger.debug(f"Disconnecting from device {self.devicename}")
        try:
            self._killConnection = True
            self.loop.create_task(self.cli.disconnect(force=True))
        except:
            self.plugin.logger.exception("Exception")

    def disconnect_linked(self):
        self.plugin.logger.debug(f"Disconnecting linked devices from {self.devicename}")
        try:
            for more_devs in indigo.devices.iter("self"):
                if 'linkedPrimaryIndigoDeviceId' in more_devs.pluginProps:
                    if str(self.deviceid) == str(more_devs.ownerProps['linkedPrimaryIndigoDeviceId']):
                        # self.logger.error(f"{device.id=} {more_devs.ownerProps['linkedPrimaryIndigoDeviceId']}")
                        more_devs.updateStateImageOnServer(indigo.kStateImageSel.PowerOff)
                        more_devs.updateStateOnServer(key="deviceIsOnline", value=False)
                        more_devs.updateStateOnServer(key="deviceStatus", value="Offline")
                        more_devs.setErrorStateOnServer("Core Device Offline.")
        except:
            self.plugin.logger.exception("Exception")

    def enable_linked(self):
        self.plugin.logger.debug(f"Enabling linked devices from {self.devicename}")
        try:
            for more_devs in indigo.devices.iter("self"):
                if 'linkedPrimaryIndigoDeviceId' in more_devs.pluginProps:
                    if str(self.deviceid) == str(more_devs.ownerProps['linkedPrimaryIndigoDeviceId']):
                        # self.logger.error(f"{device.id=} {more_devs.ownerProps['linkedPrimaryIndigoDeviceId']}")
                        more_devs.updateStateImageOnServer(indigo.kStateImageSel.PowerOff)
                        more_devs.updateStateOnServer(key="deviceIsOnline", value=True)
                        more_devs.updateStateOnServer(key="deviceStatus", value="Online")
                        more_devs.setErrorStateOnServer(None)
        except:
            self.plugin.logger.exception("Exception")

    async def loop_esphome(self, cli, deviceid):

        mainESPCoredevice = indigo.devices[deviceid]
        self.plugin.logger.debug(f"Loop ESPHOME Started for {mainESPCoredevice.name}.")
        timeretry = 10
        retries = 0
        while True:
            try:
                await asyncio.sleep(0.25)
                if timeretry > 600:
                    timeretry = 60

                self.plugin.logger.debug("Running connect")
                await cli.connect(login=True)

                api_version = self.cli.api_version
                device_info = await cli.device_info()

                entities,services = await cli.list_entities_services()
                self.plugin.logger.debug(f"\nEntities\n{entities}")
                self.plugin.logger.debug(f"\nServices\n{services}")

                ## connected successful and device_info and entities/services downloaded.
                ## check whether devices created
                deviceSetup = mainESPCoredevice.pluginProps.get("deviceSetup", True)
                self.plugin.logger.debug(f"deviceSetup: {deviceSetup}")
                if deviceSetup == "false" or deviceSetup == False:
                    self.plugin.logger.debug("*******************  Setup Devices *********************")
                    await self.setupDevices(mainESPCoredevice, device_info, entities, services, api_version)
                else:
                    await self.updateDeviceInfo(mainESPCoredevice, device_info, api_version)

                self.plugin.logger.info(f"Now subscribing to State Changes for {mainESPCoredevice.name}")
                await self.cli.subscribe_states(self.change_callback)

                while True:
                    cli._check_authenticated()  ## Causes exception when not connected.
                    await asyncio.sleep(5)

            except aioesphomeapi.core.TimeoutAPIError:
                self.plugin.logger.debug("Timeout Exception.  Retry")
            except aioesphomeapi.core.SocketAPIError:
                self.plugin.logger.debug(f"Timeout Exception. {self.devicename} Retry")
            except aioesphomeapi.core.APIConnectionError:
                self.plugin.logger.debug(f"Timeout Exception. {self.devicename}  Retry")
            except Exception:
                self.plugin.logger.debug("Exception in Loop_ATV:  Should restart.", exc_info=True)

            if self._killConnection:
                self.plugin.logger.debug("Kill Connection actioned.  Loop should now die.")
                break

            mainESPCoredevice.updateStateOnServer(key="deviceIsOnline", value=False)
            mainESPCoredevice.updateStateOnServer(key="deviceStatus", value="Offline")
            mainESPCoredevice.updateStateImageOnServer(indigo.kStateImageSel.PowerOff)
            self.disconnect_linked()

            await asyncio.sleep(15)

        ################################################################################

        ################################################################################
class Plugin(indigo.PluginBase):
    ########################################
    def __init__(self, plugin_id, plugin_display_name, plugin_version, plugin_prefs):
        super().__init__(plugin_id, plugin_display_name, plugin_version, plugin_prefs)
        self.debug = True

        # Thread for each ESP connection device, for asyncio
        self.ESPHomeThreads = []

        ################################################################################
        # Setup Logging
        ################################################################################
        self.logger.setLevel(logging.DEBUG)
        try:
            self.logLevel = int(self.pluginPrefs["showDebugLevel"])
            self.fileloglevel = int(self.pluginPrefs["showDebugFileLevel"])
        except:
            self.logLevel = logging.INFO
            self.fileloglevel = logging.DEBUG

        self.logger.removeHandler(self.indigo_log_handler)

        self.indigo_log_handler = IndigoLogHandler(plugin_display_name, logging.INFO)
        ifmt = logging.Formatter("%(message)s")
        self.indigo_log_handler.setFormatter(ifmt)
        self.indigo_log_handler.setLevel(self.logLevel)
        self.logger.addHandler(self.indigo_log_handler)

        pfmt = logging.Formatter('%(asctime)s.%(msecs)03d\t%(levelname)s\t%(name)s.%(funcName)s:\t%(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        self.plugin_file_handler.setFormatter(pfmt)
        self.plugin_file_handler.setLevel(self.fileloglevel)

        logging.getLogger("zeroconf").addHandler(self.plugin_file_handler)

        ################################################################################
        # Finish Logging changes
        ################################################################################

        self.logger.debug(u"logLevel = " + str(self.logLevel))

        self.logger.info("{0:=^130}".format(" Initializing New Plugin Session "))
        self.logger.info("{0:<30} {1}".format("Plugin name:", plugin_display_name))
        self.logger.info("{0:<30} {1}".format("Plugin version:", plugin_version))
        self.logger.info("{0:<30} {1}".format("Plugin ID:", plugin_id))
        self.logger.info("{0:<30} {1}".format("Indigo version:", indigo.server.version))
        self.logger.info("{0:<30} {1}".format("Python version:", sys.version.replace('\n', '')))
        self.logger.info("{0:<30} {1}".format("Python Directory:", sys.prefix.replace('\n', '')))
        self.logger.info("")
        self.pluginprefDirectory = '{}/Preferences/Plugins/com.GlennNZ.indigoplugin.ESPHome4Indigo'.format(indigo.server.getInstallFolderPath())

        self.debug1 = self.pluginPrefs.get('debug1', False)
        self.debug2 = self.pluginPrefs.get('debug2', False)
        self.debug3 = self.pluginPrefs.get('debug3', False)
        self.debug4 = self.pluginPrefs.get('debug4', False)
        self.debug5 = self.pluginPrefs.get('debug5', False)
        self.debug6 = self.pluginPrefs.get('debug6', False)
        self.debug7 = self.pluginPrefs.get('debug7', False)
        self.debug8 = self.pluginPrefs.get('debug8', False)
        self.debug9 = self.pluginPrefs.get('debug9', False)
        self.debug10 = self.pluginPrefs.get('debug10', False)
        self._event_loop = None
        if self.debug3:
            logging.getLogger("Plugin.HomeKit_pyHap").setLevel(logging.DEBUG)
        else:
            logging.getLogger("Plugin.HomeKit_pyHap").setLevel(logging.INFO)

    def closedPrefsConfigUi(self, valuesDict, userCancelled):
        self.logger.debug(u"closedPrefsConfigUi() method called.")
        if self.debug1:
            self.logger.debug(f"valuesDict\n {valuesDict}")
        if userCancelled:
            self.debugLog(u"User prefs dialog cancelled.")
        if not userCancelled:
            self.logLevel = int(valuesDict.get("showDebugLevel", '5'))
            self.fileloglevel = int(valuesDict.get("showDebugFileLevel", '5'))
            self.debug1 = valuesDict.get('debug1', False)
            self.debug2 = valuesDict.get('debug2', False)
            self.debug3 = valuesDict.get('debug3', False)
            self.debug4 = valuesDict.get('debug4', False)
            self.debug5 = valuesDict.get('debug5', False)
            self.debug6 = valuesDict.get('debug6', False)
            self.debug7 = valuesDict.get('debug7', False)
            self.debug8 = valuesDict.get('debug8', False)
            self.debug9 = valuesDict.get('debug9', False)
            self.debug10 = valuesDict.get('debug10', False)

            self.indigo_log_handler.setLevel(self.logLevel)
            self.plugin_file_handler.setLevel(self.fileloglevel)

            if self.debug10:
                logging.getLogger("aioesphomeapi").setLevel(logging.DEBUG)
            else:
                logging.getLogger("aioesphomeapi").setLevel(logging.ERROR)

            self.logger.debug(u"logLevel = " + str(self.logLevel))
            self.logger.debug(u"User prefs saved.")
            self.logger.debug(u"Debugging on (Level: {0})".format(self.logLevel))
        return True
    ########################################
    def startup(self):
        self.logger.debug("startup called")

        self._event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._event_loop)
        self._async_thread = threading.Thread(target=self._run_async_thread)
        self._async_thread.start()

    def shutdown(self):
        self.logger.debug("shutdown called")

    def _run_async_thread(self):
        self.logger.debug("_run_async_thread starting")
        self._event_loop.create_task(self._async_start())
        self._event_loop.run_until_complete(self._async_stop())
        self._event_loop.close()

    async def _async_start(self):
        self.logger.debug("_async_start")
        self.logger.debug("Starting event loop and setting up any connections")
        # add things you need to do at the start of the plugin here
    async def _async_stop(self):
        while True:
            await asyncio.sleep(5.0)
            if self.stopThread:
                break

    async def _async_start(self):
        self.logger.debug("_async_start")
        self.logger.debug("Starting event loop and setting up any connections")
        # add things you need to do at the start of the plugin here
    ########################################
    # deviceStartComm() is called on application launch for all of our plugin defined
    # devices, and it is called when a new device is created immediately after its
    # UI settings dialog has been validated. This is a good place to force any properties
    # we need the device to have, and to cleanup old properties.
    def deviceStopComm(self, device):
        try:
            self.logger.debug(f"{device.name}: Stopping {device.deviceTypeId} Device {device.id}")

            for i in range(len(self.ESPHomeThreads) - 1, -1, -1):
                if int(self.ESPHomeThreads[i].deviceid)== int(device.id):
                    self.logger.debug(f"{self.ESPHomeThreads[i].deviceid} and device id {device.id}")
                    self.ESPHomeThreads[i].disconnect()
                    del self.ESPHomeThreads[i]
                    self.logger.info(f"Removed ESPHome Manager for device: {device.name}")
                    device.updateStateImageOnServer(indigo.kStateImageSel.PowerOff)
                    device.updateStateOnServer(key="deviceStatus", value="ShutDown")
                    ## Shutdown linked devices
                    for more_devs in indigo.devices.iter("self"):
                        if 'linkedPrimaryIndigoDeviceId' in more_devs.pluginProps:
                            if str(device.id) == str(more_devs.ownerProps['linkedPrimaryIndigoDeviceId']):
                                #self.logger.error(f"{device.id=} {more_devs.ownerProps['linkedPrimaryIndigoDeviceId']}")
                                more_devs.updateStateImageOnServer(indigo.kStateImageSel.PowerOff)
                                more_devs.updateStateOnServer(key="deviceIsOnline", value=False)
                                more_devs.updateStateOnServer(key="deviceStatus", value="Offline")
                                more_devs.setErrorStateOnServer("Core Device Offline.")


        except:
            self.logger.debug("Exception in DeviceStopCom \n", exc_info=True)

    def deviceStartComm(self, device):
        try:
            self.logger.debug(f"{device.name}: Starting {device.deviceTypeId} Device {device.id} ")
            ipaddress = device.pluginProps.get("ESPHomeAddress","")
            if self.debug1:
                self.logger.debug(f"{device}")
            device.stateListOrDisplayStateIdChanged()
            if device.deviceTypeId == 'espHomeMainDevice':
                if device.enabled and ipaddress !="":
                    device.updateStateOnServer(key="deviceStatus", value="Starting Up")
                    device.updateStateImageOnServer(indigo.kStateImageSel.PowerOff)
                    self.ESPHomeThreads.append(ESPHome4Indigo(self, self._event_loop, device.id, ipaddress, "6053", "", device.name ) )
                # __init__(self, plugin, loop, deviceid, host, port, password, devicename):
                else:
                    device.setErrorStateOnServer(None)
                    device.updateStateImageOnServer(indigo.kStateImageSel.PowerOff)
            device.setErrorStateOnServer(None)

        except:
            self.logger.exception("Exception in Device Start:")

    ########################################
    def validateDeviceConfigUi(self, values_dict, type_id, dev_id):
        return (True, values_dict)

    def Menu_showCore(self, *args, **kwargs):
        self.logger.debug("menu run")
        for thingies in self.ESPHomeThreads:
            self.logger.debug(f"{thingies}")

    ########################################
    # Relay / Dimmer Action callback
    ######################
    def actionControlDevice(self, action, dev):
        ###### TURN ON ######
        for ESPHomethreads in self.ESPHomeThreads:
            if action.deviceAction == indigo.kDeviceAction.TurnOn:
            # Command hardware module (dev) to turn ON here:
            # ** IMPLEMENT ME **
                if dev.deviceTypeId =="ESPswitchType":
                    if str(ESPHomethreads.deviceid) == str(dev.pluginProps['linkedPrimaryIndigoDeviceId']):
                        ESPHomethreads.switch_command(key=int(dev.states['key']),state=True)
                        self.logger.info(f"sent \"{dev.name}\" on")
                        dev.updateStateOnServer("onOffState", True)
        ###### TURN OFF ######
            elif action.deviceAction == indigo.kDeviceAction.TurnOff:
            # Command hardware module (dev) to turn OFF here:
                if dev.deviceTypeId =="ESPswitchType":
                    if str(ESPHomethreads.deviceid) == str(dev.pluginProps['linkedPrimaryIndigoDeviceId']):
                        ESPHomethreads.switch_command(key=int(dev.states['key']),state=False)
                        self.logger.info(f"sent \"{dev.name}\" off")
                        dev.updateStateOnServer("onOffState", False)

        ###### LOCK ######
            if action.deviceAction == indigo.kDeviceAction.Lock:
                # Command hardware module (dev) to LOCK here:
                # ** IMPLEMENT ME **
                send_success = True        # Set to False if it failed.

                if send_success:
                    # If success then log that the command was successfully sent.
                    self.logger.info(f"Not implemented \"{dev.name}\" lock")

                    # And then tell the Indigo Server to update the state.
                    dev.updateStateOnServer("onOffState", True)
                else:
                    # Else log failure but do NOT update state on Indigo Server.
                    self.logger.error(f"send \"{dev.name}\" lock failed")

            ###### UNLOCK ######
            elif action.deviceAction == indigo.kDeviceAction.Unlock:
                # Command hardware module (dev) to turn UNLOCK here:
                # ** IMPLEMENT ME **
                send_success = True        # Set to False if it failed.

                if send_success:
                    # If success then log that the command was successfully sent.
                    self.logger.info(f"sent \"{dev.name}\" unlock")

                    # And then tell the Indigo Server to update the state:
                    dev.updateStateOnServer("onOffState", False)
                else:
                    # Else log failure but do NOT update state on Indigo Server.
                    self.logger.error(f"send \"{dev.name}\" unlock failed")

            ###### TOGGLE ######
            if action.deviceAction == indigo.kDeviceAction.Toggle:
                # Command hardware module (dev) to toggle here:
                # ** IMPLEMENT ME **
                new_on_state = not dev.onState

                if dev.deviceTypeId == "ESPswitchType":
                    if str(ESPHomethreads.deviceid) == str(dev.pluginProps['linkedPrimaryIndigoDeviceId']):
                        ESPHomethreads.switch_command(key=int(dev.states['key']), state=new_on_state)
                        self.logger.info(f"sent \"{dev.name}\" off")
                        dev.updateStateOnServer("onOffState", new_on_state)
                    # If success then log that the command was successfully sent.
                        self.logger.info(f"sent \"{dev.name}\" toggle")
                    # And then tell the Indigo Server to update the state:
                        dev.updateStateOnServer("onOffState", new_on_state)

            ###### SET BRIGHTNESS ######
            elif action.deviceAction == indigo.kDeviceAction.SetBrightness:
                # Command hardware module (dev) to set brightness here:
                # ** IMPLEMENT ME **
                new_brightness = action.actionValue
                send_success = True        # Set to False if it failed.

                if send_success:
                    # If success then log that the command was successfully sent.
                    self.logger.info(f"sent \"{dev.name}\" set brightness to {new_brightness}")

                    # And then tell the Indigo Server to update the state:
                    dev.updateStateOnServer("brightnessLevel", new_brightness)
                else:
                    # Else log failure but do NOT update state on Indigo Server.
                    self.logger.error(f"send \"{dev.name}\" set brightness to {new_brightness} failed")

            ###### BRIGHTEN BY ######
            elif action.deviceAction == indigo.kDeviceAction.BrightenBy:
                # Command hardware module (dev) to do a relative brighten here:
                # ** IMPLEMENT ME **
                new_brightness = min(dev.brightness + action.actionValue, 100)
                send_success = True        # Set to False if it failed.

                if send_success:
                    # If success then log that the command was successfully sent.
                    self.logger.info(f"sent \"{dev.name}\" brighten to {new_brightness}")

                    # And then tell the Indigo Server to update the state:
                    dev.updateStateOnServer("brightnessLevel", new_brightness)
                else:
                    # Else log failure but do NOT update state on Indigo Server.
                    self.logger.error(f"send \"{dev.name}\" brighten to {new_brightness} failed")

            ###### DIM BY ######
            elif action.deviceAction == indigo.kDeviceAction.DimBy:
                # Command hardware module (dev) to do a relative dim here:
                # ** IMPLEMENT ME **
                new_brightness = max(dev.brightness - action.actionValue, 0)
                send_success = True        # Set to False if it failed.

                if send_success:
                    # If success then log that the command was successfully sent.
                    self.logger.info(f"sent \"{dev.name}\" dim to {new_brightness}")

                    # And then tell the Indigo Server to update the state:
                    dev.updateStateOnServer("brightnessLevel", new_brightness)
                else:
                    # Else log failure but do NOT update state on Indigo Server.
                    self.logger.error(f"send \"{dev.name}\" dim to {new_brightness} failed")

            ###### SET COLOR LEVELS ######
            elif action.deviceAction == indigo.kDeviceAction.SetColorLevels:
                # action.actionValue is a dict containing the color channel key/value
                # pairs. All color channel keys (redLevel, greenLevel, etc.) are optional
                # so plugin should handle cases where some color values are not specified
                # in the action.
                action_color_vals = action.actionValue

                # Construct a list of channel keys that are possible for what this device
                # supports. It may not support RGB or may not support white levels, for
                # example, depending on how the device's properties (SupportsColor, SupportsRGB,
                # SupportsWhite, SupportsTwoWhiteLevels, SupportsWhiteTemperature) have
                # been specified.
                channel_keys = []
                using_white_channels = False
                if dev.supportsRGB:
                    channel_keys.extend(['redLevel', 'greenLevel', 'blueLevel'])
                if dev.supportsWhite:
                    channel_keys.extend(['whiteLevel'])
                    using_white_channels = True
                if dev.supportsTwoWhiteLevels:
                    channel_keys.extend(['whiteLevel2'])
                elif dev.supportsWhiteTemperature:
                    channel_keys.extend(['whiteTemperature'])
                # Note having 2 white levels (cold and warm) takes precedence over
                # the use of a white temperature value. You cannot have both, although
                # you can have a single white level and a white temperature value.

                # Next enumerate through the possible color channels and extract that
                # value from the actionValue (action_color_vals).
                kv_list = []
                result_vals = []
                for channel in channel_keys:
                    if channel in action_color_vals:
                        brightness = float(action_color_vals[channel])
                        brightness_byte = int(round(255.0 * (brightness / 100.0)))

                        # Command hardware module (dev) to change its color level here:
                        # ** IMPLEMENT ME **

                        if channel in dev.states:
                            kv_list.append({'key':channel, 'value':brightness})
                        result = str(int(round(brightness)))
                    elif channel in dev.states:
                        # If the action doesn't specify a level that is needed (say the
                        # hardware API requires a full RGB triplet to be specified, but
                        # the action only contains green level), then the plugin could
                        # extract the currently cached red and blue values from the
                        # dev.states[] dictionary:
                        cached_brightness = float(dev.states[channel])
                        cached_brightness_byte = int(round(255.0 * (cached_brightness / 100.0)))
                        # Could show in the Event Log '--' to indicate this level wasn't
                        # passed in by the action:
                        result = '--'
                        # Or could show the current device state's cached level:
                        #    result = str(int(round(cached_brightness)))

                    # Add a comma to separate the RGB values from the white values for logging.
                    if channel == 'blueLevel' and using_white_channels:
                        result += ","
                    elif channel == 'whiteTemperature' and result != '--':
                        result += " K"
                    result_vals.append(result)
                # Set to False if it failed.
                send_success = True

                result_vals_str = ' '.join(result_vals)
                if send_success:
                    # If success then log that the command was successfully sent.
                    self.logger.info(f"sent \"{dev.name}\" set color to {result_vals_str}")

                    # And then tell the Indigo Server to update the color level states:
                    if len(kv_list) > 0:
                        dev.updateStatesOnServer(kv_list)
                else:
                    # Else log failure but do NOT update state on Indigo Server.
                    self.logger.error(f"send \"{dev.name}\" set color to {result_vals_str} failed")

    ########################################
    # General Action callback
    ######################
    def actionControlUniversal(self, action, dev):
        ###### BEEP ######
        if action.deviceAction == indigo.kUniversalAction.Beep:
            # Beep the hardware module (dev) here:
            # ** IMPLEMENT ME **
            self.logger.info(f"sent \"{dev.name}\" beep request")

        ###### ENERGY UPDATE ######
        elif action.deviceAction == indigo.kUniversalAction.EnergyUpdate:
            # Request hardware module (dev) for its most recent meter data here:
            # ** IMPLEMENT ME **
            self.logger.info(f"sent \"{dev.name}\" energy update request")

        ###### ENERGY RESET ######
        elif action.deviceAction == indigo.kUniversalAction.EnergyReset:
            # Request that the hardware module (dev) reset its accumulative energy usage data here:
            # ** IMPLEMENT ME **
            self.logger.info(f"sent \"{dev.name}\" energy reset request")

        ###### STATUS REQUEST ######
        elif action.deviceAction == indigo.kUniversalAction.RequestStatus:
            # Query hardware module (dev) for its current status here:
            # ** IMPLEMENT ME **
            self.logger.info(f"sent \"{dev.name}\" status request")


    def recreateDevices(self, valuesDict, typeId, devId):

        self.logger.debug(f"reCreateDevices: {valuesDict}")
        IPaddress = valuesDict["ESPHomeAddress"]
        password = valuesDict["password"]
        valuesDict["deviceSetup"] = False

        return valuesDict

    ########################################
    # Button froms Device Config
    def testConnection(self, valuesDict, typeId, devId):
        try:
            self.logger.debug(f"testconnection: {valuesDict}")
            IPaddress = valuesDict["ESPHomeAddress"]
            password = valuesDict["password"]
            self.logger.info("Check Connection of ESPHome Device")
            self.logger.debug(f"{valuesDict}\n  and {typeId}\n  and {devId}\n")
            mainESPCoredevice = indigo.devices[devId]
            cli = APIClient(
                str(IPaddress),
                "6053",
                str(password),
                client_info=f"Indigo Setup {mainESPCoredevice.name}")
            try:
                connect = asyncio.run(cli.connect(login=True))
                return True
            except:
                self.logger.info("Failed to Connect.  Check Ip address")
                return False


            device_info = loop.run_until_complete(cli.device_info())
            self.logger.error(f"{device_info}")
            self.logger.debug(f"{device_info.esphome_version} {device_info.compilation_time} {device_info.mac_address} {device_info.name} {device_info.friendly_name} {device_info.model} {device_info.uses_password}")
           # self.plugin.logger.error(f"{device_info}")

            entities, services = loop.run_until_complete(cli.list_entities_services())
            self.logger.error(f"{entities}")
            for entity in entities:
                self.logger.error(f"{entity=}")
                self.logger.error(f"{entity.key=}")
                self.logger.error(f"{type(entity)}")
                if type(entity) == aioesphomeapi.model.SwitchInfo:
                    self.logger.error(f"{entity=}")
            self.logger.error(f"{services}")
        except:
            self.logger.exception("Exception in Test")
    ######################
    def createDevices(self, valuesDict, typeId, devId):
        #
        self.logger.info("Create ESPHome Linked Device Group if not already existing..")
        self.logger.debug(f"{valuesDict}\n  and {typeId}\n  and {devId}\n")

        mainESPCoredevice = indigo.devices[devId]
        newstates = []
        x = 1
        props_dict = dict()
        props_dict["member_of_device_group"] = True
        props_dict["linkedPrimaryIndigoDevice"] = mainESPCoredevice.name

        for device in list.entities:
            props_dict["device_number"] = x-1
            if x == 1:
                newpump = indigo.device.create(indigo.kProtocol.Plugin,
                                               deviceTypeId="ESPsensor",
                                               address = mainESPCoredevice.address,
                                               groupWithDevice=int(mainESPCoredevice.id),
                                               name=mainESPCoredevice.name+"Sensor"+str(x),
                                               folder=mainESPCoredevice.folderId,
                                               description=mainESPCoredevice.name+"-Sensor",
                                               props = props_dict
                                               )
        dev_id_list = indigo.device.getGroupList(mainESPCoredevice)
        self.logger.debug(dev_id_list)

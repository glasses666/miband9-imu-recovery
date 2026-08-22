'use strict';

// Mi Fitness / Xiaomi Smart Band 9 NFC status-only probe.
// ACTIVE CALLER SCRIPT — attach to com.mi.health main process only.
// Do NOT attach this active caller/blocker script to com.mi.health:device; a 2026-06-03 run showed
// the active blocker/caller combination can crash the device process after hooks are armed.
// For com.mi.health:device use the passive raw observer script instead.
// Safety boundary: this script only observes/calls hns.e=2,f=90 and blocks known OTA-dangerous paths.
// It must never send firmware metadata, body chunks, validate, or upgrade commands.

const CALL_ONCE_GET_OTA_STATUS = true;   // set false for passive-only capture
const EXIT_AFTER_MS = 14000;

Java.perform(function () {
  const results = {
    startedAt: Date.now(),
    callOnce: CALL_ONCE_GET_OTA_STATUS,
    dangerousCalls: [],
    outgoingF90: [],
    incomingF90: [],
    callbackResponses: [],
    statusResults: [],
    errors: [],
    instanceMode: null
  };

  function log(obj) {
    try { console.log(JSON.stringify(obj)); }
    catch (e) { console.log(JSON.stringify({ event: 'log_failed', error: String(e) })); }
  }

  function byteHex(b) {
    const v = (b & 0xff).toString(16);
    return v.length === 1 ? '0' + v : v;
  }

  function bytesToHex(arr, maxLen) {
    if (!arr) return null;
    const n = Math.min(arr.length, maxLen || arr.length);
    const out = [];
    for (let i = 0; i < n; i++) out.push(byteHex(arr[i]));
    return out.join(' ');
  }

  function field(obj, name) {
    try {
      if (!obj) return null;
      const v = obj[name];
      // Frida exposes Java fields as wrappers with .value, but method/field name collisions
      // (notably hns.e) may return a function. Fall through to reflection in that case.
      if (v !== undefined && v !== null && typeof v !== 'function') {
        if (v.value !== undefined) return v.value;
        return v;
      }
    } catch (e) {}
    try {
      const rf = obj.getClass().getDeclaredField(name);
      rf.setAccessible(true);
      const rv = rf.get(obj);
      if (rv === null || rv === undefined) return null;
      const s = String(rv);
      if (/^-?\d+$/.test(s)) return parseInt(s, 10);
      return s;
    } catch (e) { return null; }
  }

  function call0(obj, name) {
    try {
      if (!obj || !obj[name]) return null;
      return obj[name]();
    } catch (e) { return null; }
  }

  function packetInfo(packet, data) {
    const info = {
      dataLen: data ? data.length : null,
      rawHex: data ? bytesToHex(data, 96) : null,
      e: null,
      f: null,
      hasStatusField100: null,
      statusField100: null,
      hasN8q: false,
      hasB7q: false,
      hasB7qStatus: false,
      b7qStatusC: null,
      b7qStatusD: null,
      packetToString: null
    };
    try { info.packetToString = packet ? String(packet.toString()) : null; } catch (e) {}
    try { info.e = field(packet, 'e'); } catch (e) {}
    try { info.f = field(packet, 'f'); } catch (e) {}
    try { info.hasStatusField100 = !!call0(packet, 'J'); } catch (e) {}
    try { info.statusField100 = call0(packet, 's'); } catch (e) {}
    try {
      const n8q = call0(packet, 'E');
      info.hasN8q = !!n8q;
      if (n8q) {
        const b7q = call0(n8q, 'o');
        info.hasB7q = !!b7q;
        if (b7q) {
          const b7qe = field(b7q, 'f');
          info.hasB7qStatus = !!b7qe;
          if (b7qe) {
            info.b7qStatusC = field(b7qe, 'c');
            info.b7qStatusD = field(b7qe, 'd');
          }
        }
      }
    } catch (e) { info.parsePayloadError = String(e); }
    return info;
  }

  function parseHnsBytes(data) {
    try {
      const ux5 = Java.use('defpackage.ux5');
      const packet = ux5.b(data);
      if (!packet) return { parseError: 'ux5.b returned null', dataLen: data ? data.length : null, rawHex: bytesToHex(data, 96) };
      return packetInfo(packet, data);
    } catch (e) {
      return { parseError: String(e), dataLen: data ? data.length : null, rawHex: bytesToHex(data, 96) };
    }
  }

  function isDangerousHns(info) {
    // Mi Fitness official prepare/preflight boundary: hns.e=2,f=5.
    // True OTA transfer is separately blocked at executor level.
    return info && info.e === 2 && info.f === 5;
  }

  function isF90(info) { return info && info.e === 2 && info.f === 90; }

  function blockClassMethod(className, methodName) {
    try {
      const C = Java.use(className);
      C[methodName].overloads.forEach(function (ov) {
        ov.implementation = function () {
          const msg = className + '.' + methodName + ' BLOCKED';
          results.dangerousCalls.push(msg);
          log({ event: 'dangerous_blocked', method: msg });
          throw Java.use('java.lang.RuntimeException').$new(msg);
        };
      });
      log({ event: 'hooked_block', method: className + '.' + methodName });
    } catch (e) { log({ event: 'hook_block_missing', method: className + '.' + methodName, error: String(e) }); }
  }

  function blockSpecificOverload(className, methodName, argTypes, label) {
    try {
      const C = Java.use(className);
      const ov = C[methodName].overload.apply(C[methodName], argTypes);
      ov.implementation = function () {
        const msg = (label || (className + '.' + methodName)) + ' BLOCKED';
        results.dangerousCalls.push(msg);
        log({ event: 'dangerous_blocked', method: msg });
        throw Java.use('java.lang.RuntimeException').$new(msg);
      };
      log({ event: 'hooked_block', method: label || (className + '.' + methodName), overload: argTypes });
    } catch (e) { log({ event: 'hook_block_missing', method: label || (className + '.' + methodName), overload: argTypes, error: String(e) }); }
  }

  // High-level official OTA blockers.
  blockClassMethod('com.mi.fitness.checkupdate.util.DeviceSender', 'prepareOta');
  blockClassMethod('com.mi.fitness.checkupdate.util.DeviceSender', 'startOta');
  blockClassMethod('com.mi.fitness.checkupdate.util.DeviceSender', 'notifyForceUpgrade');
  blockClassMethod('com.mi.fitness.checkupdate.ui.bluetooth.BluetoothOtaManager', 'startUpgrade');
  blockClassMethod('com.mi.fitness.checkupdate.ui.bluetooth.BluetoothOtaManager', 'prepareOta');
  blockClassMethod('com.mi.fitness.checkupdate.ota.GeneralOtaExecutor', 'start');
  blockClassMethod('com.mi.fitness.checkupdate.ota.HyOtaExecutor', 'start');

  // DFU V5 dangerous command blockers (best-effort; class may not be loaded/used).
  // pm.a(yd,int,long,int,nv,o5) => D2 prepare transfer.
  // Frida sees the default-package JADX classes as short names (pm/hns/yd/...), not defpackage.*.
  blockSpecificOverload('pm', 'a', ['yd', 'int', 'long', 'int', 'nv', 'o5'], 'NewDfuProfile.D2_prepareTransfer');
  // pm.a(boolean) => D3 start transfer.
  blockSpecificOverload('pm', 'a', ['boolean'], 'NewDfuProfile.D3_startTransfer');
  // pm.h() => D5 validate.
  blockSpecificOverload('pm', 'h', [], 'NewDfuProfile.D5_validate');
  // pm.a() => D6 upgrade.
  blockSpecificOverload('pm', 'a', [], 'NewDfuProfile.D6_upgrade');
  // pm.h(byte[]) writes PKT/body data.
  blockSpecificOverload('pm', 'h', ['[B'], 'NewDfuProfile.PKT_bodyWrite');

  // Contact-layer guard: block any hns.e=2,f=5 even if not routed through DeviceSender.prepareOta.
  try {
    const DCI = Java.use('com.xiaomi.fitness.device.contact.DeviceContactImpl');
    const ov = DCI.call.overload('java.lang.String', 'hns', 'boolean', 'com.xiaomi.fitness.device.contact.export.OnSyncCallback', 'int');
    ov.implementation = function (did, packet, needResponse, callback, timeout) {
      const info = packetInfo(packet, null);
      if (isDangerousHns(info)) {
        const msg = 'DeviceContactImpl.call hns.e=2,f=5 BLOCKED';
        results.dangerousCalls.push(msg);
        log({ event: 'dangerous_blocked', method: msg, packet: info });
        throw Java.use('java.lang.RuntimeException').$new(msg);
      }
      if (isF90(info)) {
        const rec = { event: 'outgoing_f90', packet: info, needResponse: !!needResponse, timeout: timeout };
        results.outgoingF90.push(rec);
        log(rec);
      }
      return ov.call(this, did, packet, needResponse, callback, timeout);
    };
    log({ event: 'hooked_observe', method: 'DeviceContactImpl.call(hns)' });
  } catch (e) { log({ event: 'hook_observe_missing', method: 'DeviceContactImpl.call(hns)', error: String(e) }); }

  // Raw incoming HNS response capture. This is the most important hook for f90 code=1.
  try {
    const CTQ = Java.use('com.xiaomi.fitness.device.contact.remote.ContactTaskQueue');
    const ov = CTQ.dispatchMessage.overload('java.lang.String', 'int', '[B');
    ov.implementation = function (did, type, data) {
      let info = null;
      if (type === 101 && data) {
        info = parseHnsBytes(data);
        if (isF90(info) || (data.length === 7 && info.statusField100 === 1)) {
          const rec = { event: 'incoming_type101_f90_or_status1', type: type, did: '[REDACTED]', packet: info };
          results.incomingF90.push(rec);
          log(rec);
        }
      }
      return ov.call(this, did, type, data);
    };
    log({ event: 'hooked_observe', method: 'ContactTaskQueue.dispatchMessage' });
  } catch (e) { log({ event: 'hook_observe_missing', method: 'ContactTaskQueue.dispatchMessage', error: String(e) }); }

  // Callback boundary: proves packet exists even when code != 0, before ContactCallTask drops it from onSyncError.
  try {
    const CCT = Java.use('com.xiaomi.fitness.device.contact.remote.ContactCallTask');
    const ov = CCT.onReceiveResponse.overload('int', 'hns');
    ov.implementation = function (code, packet) {
      const info = packetInfo(packet, null);
      if (isF90(info) || code === 1) {
        const rec = { event: 'contact_onReceiveResponse', code: code, packet: info };
        results.callbackResponses.push(rec);
        log(rec);
      }
      return ov.call(this, code, packet);
    };
    log({ event: 'hooked_observe', method: 'ContactCallTask.onReceiveResponse(int,hns)' });
  } catch (e) { log({ event: 'hook_observe_missing', method: 'ContactCallTask.onReceiveResponse(int,hns)', error: String(e) }); }

  const Function1 = Java.use('kotlin.jvm.functions.Function1');
  const StatusCb = Java.registerClass({
    name: 'org.hermes.miband9.StatusCbRawV3' + Date.now(),
    implements: [Function1],
    methods: { invoke: [{ returnType: 'java.lang.Object', argumentTypes: ['java.lang.Object'], implementation: function (arg) {
      let s = null;
      try { s = arg ? String(arg.toString()) : null; } catch (e) { s = '<toString failed ' + e + '>'; }
      // If arg is b7q.e, fields c/d should be visible.
      const rec = { event: 'ota_status_result', value: s, c: field(arg, 'c'), d: field(arg, 'd') };
      results.statusResults.push(rec);
      log(rec);
      return null;
    }}] }
  });
  const ErrorCb = Java.registerClass({
    name: 'org.hermes.miband9.ErrorCbRawV3' + Date.now(),
    implements: [Function1],
    methods: { invoke: [{ returnType: 'java.lang.Object', argumentTypes: ['java.lang.Object'], implementation: function (arg) {
      let s = null;
      try { s = arg ? String(arg.toString()) : null; } catch (e) { s = '<toString failed ' + e + '>'; }
      const rec = { event: 'ota_status_error', value: s };
      results.errors.push(s);
      log(rec);
      return null;
    }}] }
  });

  if (CALL_ONCE_GET_OTA_STATUS) {
    try {
      const D = Java.use('com.mi.fitness.checkupdate.util.DeviceSender');
      let inst = null;
      try { inst = D.INSTANCE.value; if (inst) results.instanceMode = 'INSTANCE'; } catch (e) { results.errors.push('INSTANCE read: ' + e); }
      if (!inst) {
        try { inst = D.$new(); results.instanceMode = 'new'; } catch (e) { results.errors.push('new failed: ' + e); }
      }
      log({ event: 'calling_getOtaStatus', packet: 'hns.e=2 f=90', instanceMode: results.instanceMode, safety: 'no file/md5/size/path/body' });
      if (inst) inst.getOtaStatus(StatusCb.$new(), ErrorCb.$new());
      else throw new Error('No DeviceSender instance');
    } catch (e) { results.errors.push(String(e)); log({ event: 'call_exception', error: String(e) }); }
  } else {
    log({ event: 'passive_only', note: 'hooks armed; not calling getOtaStatus' });
  }

  setTimeout(function () { log({ event: 'summary', results: results }); }, EXIT_AFTER_MS);
});

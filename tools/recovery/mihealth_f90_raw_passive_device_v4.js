'use strict';

// Mi Fitness / Xiaomi Smart Band 9 NFC passive raw observer.
// Attach this to com.mi.health:device only. It does not call any app method and does not send packets.
// Purpose: capture type=101 HNS responses for hns.e=2,f=90 while another main-process script triggers getOtaStatus.

const EXIT_AFTER_MS = 30000;

Java.perform(function () {
  const results = { startedAt: Date.now(), incomingF90: [], callbackResponses: [], parseErrors: [] };

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
      rawHex: data ? bytesToHex(data, 128) : null,
      e: field(packet, 'e'),
      f: field(packet, 'f'),
      hasStatusField100: !!call0(packet, 'J'),
      statusField100: call0(packet, 's'),
      hasN8q: false,
      hasB7q: false,
      hasB7qStatus: false,
      b7qStatusC: null,
      b7qStatusD: null
    };
    try {
      const n8q = call0(packet, 'E');
      info.hasN8q = !!n8q;
      if (n8q) {
        const b7q = call0(n8q, 'o');
        info.hasB7q = !!b7q;
        if (b7q) {
          const b7qe = field(b7q, 'f');
          info.hasB7qStatus = !!b7qe;
          info.b7qStatusC = field(b7qe, 'c');
          info.b7qStatusD = field(b7qe, 'd');
        }
      }
    } catch (e) { info.payloadParseError = String(e); }
    return info;
  }
  function parseHnsBytes(data) {
    try {
      const ux5 = Java.use('ux5');
      const packet = ux5.b(data);
      if (!packet) return { parseError: 'ux5.b returned null', dataLen: data ? data.length : null, rawHex: bytesToHex(data, 128) };
      return packetInfo(packet, data);
    } catch (e) {
      const rec = { parseError: String(e), dataLen: data ? data.length : null, rawHex: bytesToHex(data, 128) };
      results.parseErrors.push(rec);
      return rec;
    }
  }
  function isF90(info) { return info && info.e === 2 && info.f === 90; }

  try {
    const CTQ = Java.use('com.xiaomi.fitness.device.contact.remote.ContactTaskQueue');
    const ov = CTQ.dispatchMessage.overload('java.lang.String', 'int', '[B');
    ov.implementation = function (did, type, data) {
      if (type === 101 && data) {
        const info = parseHnsBytes(data);
        if (isF90(info) || data.length === 7) {
          const rec = { event: 'incoming_type101_candidate', did: '[REDACTED]', type: type, packet: info };
          results.incomingF90.push(rec);
          log(rec);
        }
      }
      return ov.call(this, did, type, data);
    };
    log({ event: 'hooked_observe', method: 'ContactTaskQueue.dispatchMessage', mode: 'passive' });
  } catch (e) { log({ event: 'hook_observe_missing', method: 'ContactTaskQueue.dispatchMessage', error: String(e) }); }

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
    log({ event: 'hooked_observe', method: 'ContactCallTask.onReceiveResponse(int,hns)', mode: 'passive' });
  } catch (e) { log({ event: 'hook_observe_missing', method: 'ContactCallTask.onReceiveResponse(int,hns)', error: String(e) }); }

  setTimeout(function () { log({ event: 'summary', results: results }); }, EXIT_AFTER_MS);
});

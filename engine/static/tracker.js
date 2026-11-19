(function () {
  "use strict";

  var delay = window.__COLLECT_DELAY || 1500;
  var metrics = {
    timestamp: new Date().toISOString(),
    screen: {
      width: screen.width,
      height: screen.height,
      availWidth: screen.availWidth,
      availHeight: screen.availHeight,
      pixelRatio: window.devicePixelRatio || 1,
      colorDepth: screen.colorDepth
    },
    battery: {},
    accelerometer: { maxAmplitude: 0, samples: 0, averageDeviation: 0 },
    timezone: "",
    input: { mouseClicks: 0, touchEvents: 0, touchSupported: false },
    webgl: {},
    canvas: { hash: "" },
    hardware: {
      concurrency: navigator.hardwareConcurrency || 0,
      memory: navigator.deviceMemory || 0,
      platform: navigator.platform || "",
      maxTouchPoints: navigator.maxTouchPoints || 0
    },
    language: navigator.language || "",
    languages: navigator.languages ? Array.prototype.slice.call(navigator.languages) : [],
    honeyfield: { injected: false, filled: false }
  };

  try {
    metrics.timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  } catch (e) {
    metrics.timezone = "unknown";
  }

  metrics.input.touchSupported = "ontouchstart" in window || navigator.maxTouchPoints > 0;

  try {
    var canvas = document.createElement("canvas");
    var gl = canvas.getContext("webgl") || canvas.getContext("experimental-webgl");
    if (gl) {
      var dbg = gl.getExtension("WEBGL_debug_renderer_info");
      metrics.webgl = {
        vendor: dbg ? gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL) : gl.getParameter(gl.VENDOR),
        renderer: dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER)
      };
    }
  } catch (e) {
    metrics.webgl = { vendor: "error", renderer: "error" };
  }

  try {
    var c = document.createElement("canvas");
    c.width = 200;
    c.height = 50;
    var ctx = c.getContext("2d");
    ctx.textBaseline = "top";
    ctx.font = "14px Arial";
    ctx.fillStyle = "#f60";
    ctx.fillRect(125, 1, 62, 20);
    ctx.fillStyle = "#069";
    ctx.fillText("fingerprint", 2, 15);
    var dataUrl = c.toDataURL();
    var hash = 0;
    for (var i = 0; i < dataUrl.length; i++) {
      hash = ((hash << 5) - hash) + dataUrl.charCodeAt(i);
      hash = hash & hash;
    }
    metrics.canvas.hash = Math.abs(hash).toString(16);
  } catch (e) {
    metrics.canvas.hash = "error";
  }

  document.addEventListener("mousedown", function () { metrics.input.mouseClicks++; }, true);
  document.addEventListener("touchstart", function () { metrics.input.touchEvents++; }, true);

  try {
    var forms = document.getElementsByTagName("form");
    for (var fi = 0; fi < forms.length; fi++) {
      var hf = document.createElement("input");
      hf.type = "text";
      hf.name = "_hp_" + Math.random().toString(36).slice(2);
      hf.style.cssText = "position:absolute;left:-9999px;opacity:0;height:0;width:0";
      hf.tabIndex = -1;
      hf.autocomplete = "off";
      forms[fi].appendChild(hf);
      metrics.honeyfield.injected = true;
    }
  } catch (e) {}

  var accelSamples = [];
  var motionHandler = function (e) {
    var acc = e.accelerationIncludingGravity;
    if (!acc) return;
    var amplitude = Math.sqrt((acc.x || 0) ** 2 + (acc.y || 0) ** 2 + (acc.z || 0) ** 2);
    accelSamples.push(Math.abs(amplitude - 9.81));
    metrics.accelerometer.samples = accelSamples.length;
  };
  if (window.DeviceMotionEvent) {
    window.addEventListener("devicemotion", motionHandler, true);
  }

  function finish() {
    window.removeEventListener("devicemotion", motionHandler, true);
    if (accelSamples.length) {
      var sum = 0;
      for (var i = 0; i < accelSamples.length; i++) sum += accelSamples[i];
      metrics.accelerometer.averageDeviation = Math.round((sum / accelSamples.length) * 1000) / 1000;
    }
    var filled = document.querySelectorAll("input[name^='_hp_']");
    for (var hi = 0; hi < filled.length; hi++) {
      if (filled[hi].value) metrics.honeyfield.filled = true;
    }
    if (window.__TRACKER_CALLBACK) window.__TRACKER_CALLBACK(metrics);
  }

  var batteryWait = Promise.resolve();
  if (navigator.getBattery) {
    batteryWait = navigator.getBattery().then(function (bat) {
      metrics.battery = {
        charging: bat.charging,
        level: bat.level,
        chargingTime: bat.chargingTime,
        dischargingTime: bat.dischargingTime
      };
    }).catch(function () {});
  }

  batteryWait.then(function () { setTimeout(finish, delay); });
})();

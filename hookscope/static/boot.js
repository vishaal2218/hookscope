// Loaded before the app (a plain script, not a module). If the page fails to start, it says so on screen
// instead of staying blank, and tells the engine, which writes it to data/hookscope.log.
(function () {
  var BLANK_CHECK_MS = 4000;
  var MAX_REPORTS = 10;
  var sent = 0;

  function report(kind, detail) {
    if (sent++ >= MAX_REPORTS) return;
    try {
      fetch("/api/client-log", {
        method: "POST",
        headers: { "X-Hookscope": "1", "Content-Type": "application/json" },
        body: JSON.stringify({
          kind: kind,
          message: String(detail.message || detail).slice(0, 2000),
          source: String(detail.source || "").slice(0, 300),
          line: detail.line || null,
          page: location.href.slice(0, 300),
          agent: navigator.userAgent.slice(0, 300),
        }),
      });
    } catch (e) { /* nothing more we can do */ }
  }

  // Capture phase also catches script and stylesheet files that failed to load.
  window.addEventListener("error", function (e) {
    var el = e.target;
    if (el && el !== window && (el.src || el.href)) {
      report("load-failed", { message: "Could not load " + (el.src || el.href), source: el.src || el.href });
      return;
    }
    report("error", { message: e.message, source: e.filename, line: e.lineno });
  }, true);

  window.addEventListener("unhandledrejection", function (e) {
    var reason = e.reason || {};
    report("promise", { message: reason.stack || reason.message || reason });
  });

  window.addEventListener("load", function () {
    setTimeout(function () {
      var main = document.getElementById("main");
      if (!main || main.children.length) return;
      report("blank", { message: "Main area still empty " + BLANK_CHECK_MS / 1000 + " s after load" });
      var box = document.createElement("div");
      box.className = "empty";
      var title = document.createElement("h3");
      title.textContent = "The page didn't finish loading";
      var text = document.createElement("p");
      text.textContent = "Press Cmd+Shift+R to reload it. If it stays blank, quit Hookscope from the menu bar and open it again. The error has been written to Hookscope's log.";
      box.appendChild(title);
      box.appendChild(text);
      main.appendChild(box);
    }, BLANK_CHECK_MS);
  });
})();

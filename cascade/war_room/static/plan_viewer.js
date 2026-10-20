// Vendored: marked 12.0.2, mermaid 10.9.3 (see static/vendor/)
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  root.PlanViewer = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var MERMAID_FENCE_RE = /^```\s*mermaid\s*\n([\s\S]*?)^```\s*$/gm;
  var WORK_ID_FROM_PATH_RE = /^((?:epic|feat|task)_\d+)/;

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  var ALLOWED_URL_SCHEME_RE = /^(https?|mailto):/i;

  function safeUrl(href) {
    if (href == null || href === "") {
      return null;
    }
    var trimmed = String(href).trim();
    if (trimmed === "") {
      return null;
    }
    if (trimmed.charAt(0) === "#") {
      return trimmed;
    }
    if (trimmed.charAt(0) === "/") {
      return trimmed;
    }
    var schemeMatch = /^([a-z][a-z0-9+.-]*):/i.exec(trimmed);
    if (!schemeMatch) {
      return trimmed;
    }
    if (ALLOWED_URL_SCHEME_RE.test(trimmed)) {
      return trimmed;
    }
    return null;
  }

  function findMermaidFences(markdown) {
    var fences = [];
    if (markdown == null || markdown === "") {
      return fences;
    }
    var re = new RegExp(MERMAID_FENCE_RE.source, MERMAID_FENCE_RE.flags);
    var match;
    while ((match = re.exec(markdown)) !== null) {
      fences.push({
        start: match.index,
        content: match[1].replace(/\n$/, ""),
      });
    }
    return fences;
  }

  function workIdFromDocHref(href) {
    if (href == null || href === "") {
      return null;
    }
    var trimmed = String(href).trim();
    if (/^(https?:|mailto:|#|\/)/i.test(trimmed)) {
      return null;
    }
    var base = trimmed.split(/[/\\]/).pop() || "";
    var withoutExt = base.replace(/\.md$/i, "");
    var m = WORK_ID_FROM_PATH_RE.exec(withoutExt);
    return m ? m[1] : null;
  }

  function planHrefFromRelative(href) {
    var workId = workIdFromDocHref(href);
    return workId ? "/plan/" + workId : null;
  }

  function rewriteWorkDocLinks(html) {
    if (html == null || html === "") {
      return html;
    }
    return String(html).replace(
      /<a\b([^>]*?)\bhref=(["'])(.*?)\2([^>]*)>/gi,
      function (full, before, quote, href, after) {
        var planHref = planHrefFromRelative(href);
        if (!planHref) {
          return full;
        }
        return "<a" + before + "href=" + quote + planHref + quote + after + ">";
      }
    );
  }

  function offsetToSourceLine(body, offset) {
    var line = 1;
    for (var i = 0; i < offset && i < body.length; i += 1) {
      if (body.charCodeAt(i) === 10) {
        line += 1;
      }
    }
    return line;
  }

  function blockLineNumbersForBody(body) {
    var text = body != null ? String(body) : "";
    if (typeof marked === "undefined") {
      return [];
    }
    var tokens = marked.lexer(text);
    var offset = 0;
    var lines = [];
    for (var i = 0; i < tokens.length; i += 1) {
      var tok = tokens[i];
      var raw = tok.raw || "";
      if (tok.type === "space") {
        offset += raw.length;
        continue;
      }
      lines.push(offsetToSourceLine(text, offset));
      offset += raw.length;
    }
    return lines;
  }

  function dataSrcLineAttr(line) {
    return line != null ? ' data-src-line="' + line + '"' : "";
  }

  function buildMarkedParseOptions(body) {
    if (typeof marked === "undefined") {
      return null;
    }
    var text = body != null ? String(body) : "";
    var defaultRenderer = new marked.Renderer();
    var blockLines = blockLineNumbersForBody(text);
    var blockIndex = 0;

    function takeBlockLine() {
      if (blockIndex >= blockLines.length) {
        return null;
      }
      var line = blockLines[blockIndex];
      blockIndex += 1;
      return line;
    }

    var renderer = new marked.Renderer();
    renderer.html = function (rawText) {
      return escapeHtml(rawText);
    };
    renderer.link = function (href, title, linkText) {
      var safe = safeUrl(href);
      if (!safe) {
        return escapeHtml(linkText);
      }
      var out = '<a href="' + escapeHtml(safe) + '"';
      if (title) {
        out += ' title="' + escapeHtml(title) + '"';
      }
      return out + ">" + linkText + "</a>";
    };
    renderer.image = function (href, title, altText) {
      var safe = safeUrl(href);
      if (!safe) {
        return escapeHtml(altText || "");
      }
      var out = '<img src="' + escapeHtml(safe) + '" alt="' + escapeHtml(altText || "") + '"';
      if (title) {
        out += ' title="' + escapeHtml(title) + '"';
      }
      return out + ">";
    };
    renderer.code = function (codeText, lang) {
      var line = takeBlockLine();
      var language = (lang || "").trim().toLowerCase();
      if (language === "mermaid") {
        return (
          '<div class="mermaid"' +
          dataSrcLineAttr(line) +
          ">" +
          escapeHtml(codeText) +
          "</div>\n"
        );
      }
      var langAttr = language ? ' class="language-' + escapeHtml(language) + '"' : "";
      return (
        "<pre" +
        dataSrcLineAttr(line) +
        "><code" +
        langAttr +
        ">" +
        escapeHtml(codeText) +
        "</code></pre>\n"
      );
    };
    renderer.heading = function (headingText, level) {
      var line = takeBlockLine();
      return (
        "<h" +
        level +
        dataSrcLineAttr(line) +
        ">" +
        headingText +
        "</h" +
        level +
        ">\n"
      );
    };
    renderer.paragraph = function (paragraphText) {
      var line = takeBlockLine();
      return "<p" + dataSrcLineAttr(line) + ">" + paragraphText + "</p>\n";
    };
    renderer.table = function (header, tableBody) {
      var line = takeBlockLine();
      return defaultRenderer.table
        .call(this, header, tableBody)
        .replace(/^<table>/, "<table" + dataSrcLineAttr(line) + ">");
    };
    renderer.blockquote = function (quote) {
      var line = takeBlockLine();
      return "<blockquote" + dataSrcLineAttr(line) + ">\n" + quote + "</blockquote>\n";
    };
    renderer.list = function (listBody, ordered, start) {
      var line = takeBlockLine();
      var tag = ordered ? "ol" : "ul";
      var startAttr =
        ordered && start !== "" && start != null && start !== 1 ? ' start="' + start + '"' : "";
      return (
        "<" +
        tag +
        dataSrcLineAttr(line) +
        startAttr +
        ">\n" +
        listBody +
        "</" +
        tag +
        ">\n"
      );
    };
    renderer.hr = function () {
      var line = takeBlockLine();
      return "<hr" + dataSrcLineAttr(line) + ">\n";
    };
    return { gfm: true, breaks: false, renderer: renderer };
  }

  function markdownToHtml(body) {
    var options = buildMarkedParseOptions(body);
    if (!options) {
      return null;
    }
    return marked.parse(body != null ? String(body) : "", options);
  }

  function mermaidNodeHasDiagram(node) {
    return !!(node && node.querySelector && node.querySelector("svg"));
  }

  function mermaidNodeToPre(node) {
    if (mermaidNodeHasDiagram(node)) {
      return;
    }
    var pre = document.createElement("pre");
    if (node.getAttribute) {
      var srcLine = node.getAttribute("data-src-line");
      if (srcLine != null && srcLine !== "") {
        pre.setAttribute("data-src-line", srcLine);
      }
    }
    var code = document.createElement("code");
    code.textContent = node.textContent || "";
    pre.appendChild(code);
    if (node.parentNode) {
      node.parentNode.replaceChild(pre, node);
    }
  }

  function fallbackAllMermaid(container) {
    if (!container || !container.querySelectorAll) {
      return;
    }
    var nodes = container.querySelectorAll(".mermaid");
    for (var i = 0; i < nodes.length; i += 1) {
      mermaidNodeToPre(nodes[i]);
    }
  }

  var PAGE_LOAD_MS = 10000;
  var MERMAID_SCRIPT_SRC = "/static/vendor/mermaid.min.js";
  var mermaidLoadPromise = null;

  function withDeadline(work, ms) {
    var limit = ms == null ? PAGE_LOAD_MS : ms;
    return new Promise(function (resolve, reject) {
      var timer = setTimeout(function () {
        var err = new Error("Timed out after 10s");
        err.name = "TimeoutError";
        reject(err);
      }, limit);
      Promise.resolve(work).then(
        function (value) {
          clearTimeout(timer);
          resolve(value);
        },
        function (err) {
          clearTimeout(timer);
          reject(err);
        }
      );
    });
  }

  function pageLoadSignal() {
    if (typeof AbortSignal !== "undefined" && typeof AbortSignal.timeout === "function") {
      return AbortSignal.timeout(PAGE_LOAD_MS);
    }
    var controller = new AbortController();
    setTimeout(function () {
      controller.abort();
    }, PAGE_LOAD_MS);
    return controller.signal;
  }

  function loadMermaidScript(src) {
    if (typeof mermaid !== "undefined") {
      return Promise.resolve();
    }
    if (typeof document === "undefined") {
      return Promise.resolve();
    }
    if (mermaidLoadPromise) {
      return mermaidLoadPromise;
    }
    var scriptSrc = src != null ? src : MERMAID_SCRIPT_SRC;
    mermaidLoadPromise = new Promise(function (resolve) {
      var settled = false;
      function finish() {
        if (settled) return;
        settled = true;
        resolve();
      }
      var script = document.createElement("script");
      script.src = scriptSrc;
      script.onload = finish;
      script.onerror = finish;
      setTimeout(finish, PAGE_LOAD_MS);
      document.head.appendChild(script);
    });
    return mermaidLoadPromise;
  }

  function runMermaidDiagrams(container, timeoutMs) {
    var limit = timeoutMs != null ? timeoutMs : PAGE_LOAD_MS;
    if (!container) {
      return Promise.resolve();
    }
    if (typeof mermaid === "undefined") {
      fallbackAllMermaid(container);
      return Promise.resolve();
    }
    var nodes = container.querySelectorAll(".mermaid");
    if (!nodes.length) {
      return Promise.resolve();
    }
    try {
      mermaid.initialize({ startOnLoad: false, securityLevel: "strict" });
    } catch (_err) {
      fallbackAllMermaid(container);
      return Promise.resolve();
    }
    var nodeList = Array.prototype.slice.call(nodes);
    // Decode HTML entities (e.g. --&gt; → -->) into text nodes so mermaid.parse
    // sees flowchart arrows, not leftover entity markup from innerHTML.
    nodeList.forEach(function (node) {
      if (!mermaidNodeHasDiagram(node)) {
        node.textContent = node.textContent || "";
      }
    });
    var runPromise;
    try {
      runPromise = mermaid.run({ nodes: nodeList });
    } catch (_err) {
      fallbackAllMermaid(container);
      return Promise.resolve();
    }
    if (!runPromise || typeof runPromise.then !== "function") {
      return Promise.resolve();
    }
    var timeoutPromise = new Promise(function (_resolve, reject) {
      setTimeout(function () {
        reject(new Error("mermaid timeout"));
      }, limit);
    });
    return Promise.race([runPromise, timeoutPromise]).catch(function () {
      nodeList.forEach(function (node) {
        if (node.parentNode) {
          mermaidNodeToPre(node);
        }
      });
    });
  }

  function renderPlanBody(bodyEl, body, options) {
    if (!bodyEl) {
      return Promise.resolve();
    }
    var html = markdownToHtml(body);
    if (html == null) {
      bodyEl.innerHTML = "";
      var pre = document.createElement("pre");
      pre.textContent = body != null ? body : "";
      bodyEl.appendChild(pre);
      return Promise.resolve();
    }
    html = rewriteWorkDocLinks(html);
    bodyEl.innerHTML = html;
    // mermaid.run measures SVG via getBoundingClientRect. A [hidden] article is
    // display:none, so the measure throws and our fallback used to replace a
    // painted diagram with the injected stylesheet text.
    bodyEl.hidden = false;
    return loadMermaidScript(options && options.mermaidScriptSrc).then(function () {
      return runMermaidDiagrams(bodyEl, options && options.mermaidTimeoutMs);
    });
  }

  function fillHeaderElements(meta, sha, workId) {
    var title = (meta && meta.title) || workId || "Plan";
    var pageTitleEl = document.getElementById("plan-page-title");
    if (pageTitleEl) {
      pageTitleEl.textContent = title + " — Plan";
    }
    function setText(id, value) {
      var el = document.getElementById(id);
      if (el) {
        el.textContent = value;
      }
    }
    setText("plan-meta-id", (meta && meta.id) || workId);
    setText("plan-meta-title", title);
    setText("plan-meta-tier", (meta && meta.tier) || "—");
    setText("plan-meta-status", (meta && meta.status) || "—");
    setText("plan-meta-path", (meta && meta.path) || "—");
    setText("plan-meta-sha", sha != null && sha !== "" ? sha : "uncommitted");

    var parentRevNote = document.getElementById("plan-meta-parent-rev-note");
    if (parentRevNote) {
      var pinned = meta && meta.parent_rev;
      if (pinned != null && pinned !== "") {
        var shortSha = String(pinned).slice(0, 7);
        parentRevNote.textContent =
          "Parent pinned at commit " + shortSha + " (historical parent body not loaded in v1).";
        parentRevNote.hidden = false;
      } else {
        parentRevNote.textContent = "";
        parentRevNote.hidden = true;
      }
    }
  }

  function initPlanComments(workId, tier) {
    if (tier === "task") {
      return;
    }
    var panel = document.getElementById("plan-comments");
    var threadEl = document.getElementById("plan-comment-threads");
    var compose = document.getElementById("plan-comment-compose");
    var bodyInput = document.getElementById("plan-comment-body");
    var sectionInput = document.getElementById("plan-comment-section");
    var blockingInput = document.getElementById("plan-comment-blocking");
    var statusEl = document.getElementById("plan-comment-status");
    if (!panel || !threadEl || !compose || !bodyInput || !sectionInput) {
      return;
    }

    function setCommentStatus(msg, isError) {
      if (!statusEl) return;
      statusEl.textContent = msg || "";
      statusEl.classList.toggle("error", !!isError);
    }

    function renderCommentThreads(comments) {
      threadEl.innerHTML = "";
      var rows = comments || [];
      var roots = rows.filter(function (row) {
        return !row.parent;
      });
      roots.forEach(function (root) {
        var block = document.createElement("div");
        block.className = "plan-comment-thread";
        if (root.state === "resolved") {
          block.classList.add("resolved");
        }
        block.setAttribute("role", "listitem");
        block.appendChild(buildCommentNode(root));
        var replies = rows.filter(function (row) {
          return row.parent === root.id;
        });
        if (replies.length) {
          var replyWrap = document.createElement("div");
          replyWrap.className = "plan-comment-replies";
          replies.forEach(function (reply) {
            replyWrap.appendChild(buildCommentNode(reply));
          });
          block.appendChild(replyWrap);
        }
        threadEl.appendChild(block);
      });
    }

    function buildCommentNode(row) {
      var wrap = document.createElement("div");
      wrap.className = "plan-comment-entry";
      var meta = document.createElement("div");
      meta.className = "plan-comment-meta";
      meta.textContent =
        (row.author || "unknown") +
        " · " +
        (row.section || "") +
        (row.blocking ? " · blocking" : "") +
        (row.state === "resolved" ? " · resolved" : "");
      var body = document.createElement("p");
      body.className = "plan-comment-body-text";
      body.textContent = row.body || "";
      wrap.appendChild(meta);
      wrap.appendChild(body);
      return wrap;
    }

    function loadComments() {
      return fetch("/api/comments/" + encodeURIComponent(workId), {
        signal: pageLoadSignal(),
      })
        .then(function (resp) {
          if (!resp.ok) {
            throw new Error("Failed to load comments (" + resp.status + ")");
          }
          return resp.json();
        })
        .then(function (data) {
          renderCommentThreads(data.comments || []);
        });
    }

    compose.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var text = bodyInput.value.trim();
      var section = sectionInput.value.trim();
      if (!text || !section) {
        setCommentStatus("Section and comment are required.", true);
        return;
      }
      setCommentStatus("Posting…", false);
      fetch("/api/comment", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          doc_id: workId,
          section: section,
          body: text,
          blocking: !!(blockingInput && blockingInput.checked),
        }),
      })
        .then(function (resp) {
          return resp.text().then(function (raw) {
            var payload;
            try {
              payload = JSON.parse(raw);
            } catch (_e) {
              payload = { error: raw };
            }
            if (!resp.ok) {
              var errMsg =
                payload && payload.error ? payload.error : "Post failed (" + resp.status + ")";
              throw new Error(errMsg);
            }
            return payload;
          });
        })
        .then(function () {
          bodyInput.value = "";
          if (blockingInput) {
            blockingInput.checked = false;
          }
          setCommentStatus("");
          return loadComments();
        })
        .catch(function (err) {
          setCommentStatus(err && err.message ? err.message : "Post failed", true);
        });
    });

    panel.hidden = false;
    loadComments().catch(function (err) {
      setCommentStatus(err && err.message ? err.message : "Could not load comments", true);
    });
  }

  function bootstrapPlanViewer() {
    var workId = document.body.getAttribute("data-work-id");
    if (!workId) {
      return;
    }

    var loadingEl = document.getElementById("plan-loading");
    var errorEl = document.getElementById("plan-error");
    var bodyEl = document.getElementById("plan-body");

    function showError(message) {
      if (loadingEl) {
        loadingEl.hidden = true;
        loadingEl.removeAttribute("aria-busy");
      }
      if (errorEl) {
        errorEl.textContent = message;
        errorEl.hidden = false;
      }
    }

    var loadWork = fetch("/api/doc/" + encodeURIComponent(workId), {
      signal: pageLoadSignal(),
    })
      .then(function (resp) {
        if (!resp.ok) {
          throw new Error("Failed to load plan (" + resp.status + ")");
        }
        return resp.json();
      })
      .then(function (doc) {
        var meta = doc.meta || {};
        fillHeaderElements(meta, doc.sha, workId);
        return renderPlanBody(bodyEl, doc.body).then(function () {
          if (loadingEl) {
            loadingEl.hidden = true;
            loadingEl.removeAttribute("aria-busy");
          }
          if (bodyEl) {
            bodyEl.hidden = false;
          }
          initPlanComments(workId, meta.tier);
        });
      });
    withDeadline(loadWork).catch(function (err) {
      var timedOut = err && (err.name === "TimeoutError" || err.name === "AbortError");
      showError(timedOut ? "Timed out after 10s" : err && err.message ? err.message : "Failed to load plan");
    });
  }

  if (typeof document !== "undefined" && document.body) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", bootstrapPlanViewer);
    } else {
      bootstrapPlanViewer();
    }
  }

  return {
    escapeHtml: escapeHtml,
    safeUrl: safeUrl,
    blockLineNumbersForBody: blockLineNumbersForBody,
    findMermaidFences: findMermaidFences,
    workIdFromDocHref: workIdFromDocHref,
    planHrefFromRelative: planHrefFromRelative,
    rewriteWorkDocLinks: rewriteWorkDocLinks,
    markdownToHtml: markdownToHtml,
    mermaidNodeHasDiagram: mermaidNodeHasDiagram,
    renderPlanBody: renderPlanBody,
    runMermaidDiagrams: runMermaidDiagrams,
    loadMermaidScript: loadMermaidScript,
    MERMAID_SCRIPT_SRC: MERMAID_SCRIPT_SRC,
  };
});

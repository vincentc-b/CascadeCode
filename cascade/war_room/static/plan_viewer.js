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

  var SECTION_SLUG_NON = /[^a-z0-9]+/g;

  function sectionSlug(heading) {
    var slug = String(heading != null ? heading : "")
      .trim()
      .toLowerCase()
      .replace(SECTION_SLUG_NON, "-")
      .replace(/^-+|-+$/g, "");
    return slug;
  }

  function blockSourceRangesForBody(body) {
    var text = body != null ? String(body) : "";
    if (typeof marked === "undefined") {
      return [];
    }
    var tokens = marked.lexer(text);
    var offset = 0;
    var ranges = [];
    for (var i = 0; i < tokens.length; i += 1) {
      var tok = tokens[i];
      var raw = tok.raw || "";
      if (tok.type === "space") {
        offset += raw.length;
        continue;
      }
      var startLine = offsetToSourceLine(text, offset);
      var endOffset = offset + raw.length;
      var endLine = offsetToSourceLine(text, Math.max(offset, endOffset - 1));
      ranges.push({ lineStart: startLine, lineEnd: endLine });
      offset = endOffset;
    }
    return ranges;
  }

  function headingIndexForBody(body) {
    var lines = String(body != null ? body : "").split("\n");
    var headings = [];
    var firstH2Line = null;
    for (var i = 0; i < lines.length; i += 1) {
      var match = /^(#{1,6})\s+(.+?)\s*$/.exec(lines[i]);
      if (!match) {
        continue;
      }
      var level = match[1].length;
      var title = match[2];
      var lineNum = i + 1;
      if (level >= 2 && firstH2Line === null) {
        firstH2Line = lineNum;
      }
      headings.push({ line: lineNum, level: level, title: title, slug: sectionSlug(title) });
    }
    return { headings: headings, firstH2Line: firstH2Line };
  }

  function sectionForSourceLine(body, line) {
    var idx = headingIndexForBody(body);
    var headings = idx.headings;
    var firstH2 = idx.firstH2Line;
    var lineNum = line != null ? line : 1;
    var h1 = null;
    var nearestH2Plus = null;
    for (var i = 0; i < headings.length; i += 1) {
      var h = headings[i];
      if (h.line > lineNum) {
        break;
      }
      if (h.level === 1) {
        h1 = h;
      }
      if (h.level >= 2) {
        nearestH2Plus = h;
      }
    }
    if (firstH2 !== null && lineNum < firstH2) {
      if (h1 && h1.slug) {
        return h1.slug;
      }
      return "general";
    }
    if (nearestH2Plus && nearestH2Plus.slug) {
      return nearestH2Plus.slug;
    }
    if (h1 && h1.slug) {
      return h1.slug;
    }
    return "general";
  }

  function lineRangeForSectionSlug(body, slug) {
    var want = String(slug != null ? slug : "");
    if (!want) {
      return null;
    }
    var lines = String(body != null ? body : "").split("\n");
    var idx = headingIndexForBody(body);
    var headings = idx.headings;
    for (var i = 0; i < headings.length; i += 1) {
      var h = headings[i];
      if (h.level < 2 || h.slug !== want) {
        continue;
      }
      var startLine = h.line;
      var endLine = lines.length;
      for (var j = i + 1; j < headings.length; j += 1) {
        if (headings[j].level <= h.level) {
          endLine = headings[j].line - 1;
          break;
        }
      }
      return { headingLine: h.line, startLine: startLine, endLine: endLine };
    }
    return null;
  }

  function isSectionThread(body, section) {
    return lineRangeForSectionSlug(body, section) != null;
  }

  function findAnchorLineInRange(body, anchor, startLine, endLine) {
    if (anchor == null || String(anchor).trim() === "") {
      return null;
    }
    var lines = String(body != null ? body : "").split("\n");
    var start = Math.max(1, startLine || 1);
    var end = Math.min(lines.length, endLine != null ? endLine : lines.length);
    if (start > end) {
      return null;
    }
    var chunk = lines.slice(start - 1, end).join("\n");
    var needle = String(anchor);
    var pos = chunk.indexOf(needle);
    if (pos === -1) {
      return null;
    }
    var before = chunk.slice(0, pos);
    return start + before.split("\n").length - 1;
  }

  function blockStartLineForSourceLine(body, line) {
    var lineNum = line != null ? line : 1;
    var ranges = blockSourceRangesForBody(body);
    for (var i = 0; i < ranges.length; i += 1) {
      if (lineNum >= ranges[i].lineStart && lineNum <= ranges[i].lineEnd) {
        return ranges[i].lineStart;
      }
    }
    var best = null;
    for (var j = 0; j < ranges.length; j += 1) {
      if (ranges[j].lineStart <= lineNum) {
        best = ranges[j].lineStart;
      }
    }
    return best != null ? best : lineNum;
  }

  function placementForRootThread(root, body, currentSha) {
    var storedLine = root && root.line_start != null ? root.line_start : 1;
    var threadSha = root && root.doc_sha != null ? String(root.doc_sha) : "";
    var current = currentSha != null ? String(currentSha) : "";
    if (threadSha !== "" && threadSha === current) {
      return { gutterLine: storedLine, outdated: false };
    }
    var anchor = root && root.anchor;
    var section = root && root.section != null ? root.section : "";
    var lines = String(body != null ? body : "").split("\n");
    var sectionRange = lineRangeForSectionSlug(body, section);
    if (sectionRange) {
      var inSection = findAnchorLineInRange(
        body,
        anchor,
        sectionRange.startLine,
        sectionRange.endLine
      );
      if (inSection != null) {
        return { gutterLine: inSection, outdated: false };
      }
      return { gutterLine: sectionRange.headingLine, outdated: true };
    }
    var inDoc = findAnchorLineInRange(body, anchor, 1, lines.length);
    if (inDoc != null) {
      return { gutterLine: inDoc, outdated: false };
    }
    return { gutterLine: 1, outdated: true };
  }

  function lineEndForBlockStart(body, lineStart) {
    var ranges = blockSourceRangesForBody(body);
    for (var i = 0; i < ranges.length; i += 1) {
      if (ranges[i].lineStart === lineStart) {
        return ranges[i].lineEnd;
      }
    }
    return lineStart;
  }

  function snippetFromLines(body, lineStart, lineEnd, maxLen) {
    var lines = String(body != null ? body : "").split("\n");
    var start = Math.max(1, lineStart || 1);
    var end = Math.min(lines.length, lineEnd || start);
    var chunk = lines.slice(start - 1, end).join("\n").trim();
    var limit = maxLen != null ? maxLen : 120;
    if (chunk.length > limit) {
      chunk = chunk.slice(0, limit);
    }
    return chunk;
  }

  function rootCommentPayload(workId, text, target, docSha, blocking) {
    return {
      doc_id: workId,
      section: target && target.section ? target.section : "general",
      body: text,
      line_start: target && target.line_start != null ? target.line_start : null,
      line_end: target && target.line_end != null ? target.line_end : null,
      anchor: target && target.anchor ? target.anchor : null,
      doc_sha: docSha || null,
      blocking: !!blocking,
    };
  }

  function srcLineFromDomNode(node, bodyEl) {
    var el = node && node.nodeType === 1 ? node : node && node.parentElement;
    while (el && el !== bodyEl) {
      if (el.getAttribute && el.hasAttribute("data-src-line")) {
        var parsed = parseInt(el.getAttribute("data-src-line"), 10);
        return Number.isFinite(parsed) ? parsed : null;
      }
      el = el.parentElement;
    }
    return null;
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

  function postJson(path, payload) {
    return fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then(function (resp) {
      return resp.text().then(function (raw) {
        var parsed;
        try {
          parsed = JSON.parse(raw);
        } catch (_e) {
          parsed = { error: raw };
        }
        if (!resp.ok) {
          var err = new Error(parsed.error || resp.statusText);
          err.status = resp.status;
          err.body = parsed;
          throw err;
        }
        return parsed;
      });
    });
  }

  function initEpicPlanReadinessChrome(workId, readiness, options) {
    options = options || {};
    var EpicPlanReadinessUi = options.EpicPlanReadinessUi || globalThis.EpicPlanReadinessUi;
    var host = document.getElementById("epic-plan-readiness-host");
    if (!host || !EpicPlanReadinessUi || !readiness) {
      return null;
    }

    host.hidden = false;
    host.replaceChildren();
    var chrome = EpicPlanReadinessUi.renderPlanReadinessBar(document, readiness, workId);
    host.appendChild(chrome.bar);

    function refreshReadiness() {
      return fetch("/api/doc/" + encodeURIComponent(workId), {
        signal: pageLoadSignal(),
      })
        .then(function (resp) {
          if (!resp.ok) {
            throw new Error("Failed to refresh readiness (" + resp.status + ")");
          }
          return resp.json();
        })
        .then(function (doc) {
          if (doc.plan_readiness) {
            EpicPlanReadinessUi.applyReadinessToPlanBar(
              chrome,
              document,
              doc.plan_readiness,
              workId
            );
          }
        });
    }

    chrome.approveButton.addEventListener("click", function () {
      if (chrome.approveButton.disabled) return;
      chrome.errorElement.hidden = true;
      chrome.errorElement.textContent = "";
      chrome.approveButton.disabled = true;
      postJson("/api/approve_epic_plan", { id: workId })
        .then(function (body) {
          if (!body || body.ok !== true) {
            throw new Error("Unexpected approval response");
          }
          chrome.approveButton.textContent = "Approved";
          chrome.approveButton.classList.add("approval-confirmed");
          chrome.approveButton.disabled = true;
          chrome.approveButton.setAttribute("aria-disabled", "true");
          if (chrome.disabledReasonNote) {
            chrome.disabledReasonNote.hidden = true;
          }
        })
        .catch(function (err) {
          chrome.errorElement.textContent = EpicPlanReadinessUi.staleApprovalErrorMessage(err);
          chrome.errorElement.hidden = false;
          return refreshReadiness().catch(function () {
            if (chrome.approveButton.textContent === "Approve plan") {
              chrome.approveButton.disabled = false;
            }
          });
        });
    });

    return { chrome: chrome, refreshReadiness: refreshReadiness };
  }

  function initDependencyReviewChrome(workId, projection, readinessMount, options) {
    options = options || {};
    var DependencyReviewUi = options.DependencyReviewUi || globalThis.DependencyReviewUi;
    var host = document.getElementById("dependency-review-host");
    if (!host || !DependencyReviewUi || !projection) return null;
    host.hidden = false;
    return DependencyReviewUi.renderInto(document, host, projection, {
      post: options.post,
      onProjection: function (next) {
        if (
          readinessMount && next.planning_readiness &&
          globalThis.EpicPlanReadinessUi
        ) {
          globalThis.EpicPlanReadinessUi.applyReadinessToPlanBar(
            readinessMount.chrome,
            document,
            next.planning_readiness,
            workId
          );
        }
        if (typeof options.onProjection === "function") options.onProjection(next);
      },
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

  function groupCommentThreads(comments) {
    // Sort a copy: API order must not determine roots, replies, or cycle fallback.
    function compare(a, b) {
      var delta = (Date.parse(a.created) || 0) - (Date.parse(b.created) || 0);
      return delta || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
    }
    var rows = (comments || []).slice().sort(compare);
    var byId = new Map();
    rows.forEach(function (row) { byId.set(row.id, row); });
    var rootById = new Map();
    rows.forEach(function (row) {
      var path = [];
      var seen = new Map();
      var current = row;
      var root;
      while (!root) {
        if (rootById.has(current.id)) {
          root = rootById.get(current.id);
          break;
        }
        if (seen.has(current.id)) {
          // Break the cycle at its oldest member, independent of input order.
          root = path.slice(seen.get(current.id)).sort(compare)[0];
          break;
        }
        seen.set(current.id, path.length);
        path.push(current);
        if (!current.parent || !byId.has(current.parent)) {
          root = current;
          break;
        }
        current = byId.get(current.parent);
      }
      path.forEach(function (member) { rootById.set(member.id, root); });
    });
    var threads = new Map();
    rows.forEach(function (row) {
      var root = rootById.get(row.id);
      if (!threads.has(root.id)) threads.set(root.id, { root: root, replies: [] });
      if (row.id !== root.id) threads.get(root.id).replies.push(row);
    });
    return Array.from(threads.values()).sort(function (a, b) { return compare(a.root, b.root); });
  }

  function collectPreservedThreadExtras(container) {
    var map = {};
    if (!container || !container.querySelectorAll) {
      return map;
    }
    var nodes = container.querySelectorAll(".plan-comment-thread[data-comment-id]");
    for (var i = 0; i < nodes.length; i += 1) {
      var el = nodes[i];
      var id = el.getAttribute("data-comment-id");
      if (!id) {
        continue;
      }
      var extras = [];
      var children = el.children;
      for (var c = 0; c < children.length; c += 1) {
        var child = children[c];
        if (child.classList.contains("plan-comment-entry")) {
          continue;
        }
        if (child.classList.contains("plan-comment-replies")) {
          continue;
        }
        if (child.classList.contains("plan-comment-reply-form")) {
          continue;
        }
        if (child.classList.contains("plan-comment-resolve")) {
          continue;
        }
        extras.push(child.cloneNode(true));
      }
      if (extras.length) {
        map[id] = extras;
      }
    }
    return map;
  }

  function mergePreservedThreadExtras(into, from) {
    if (!from) {
      return into;
    }
    Object.keys(from).forEach(function (id) {
      if (!into[id]) {
        into[id] = from[id];
        return;
      }
      into[id] = into[id].concat(from[id]);
    });
    return into;
  }

  function collectReplyDrafts(container) {
    var replyDrafts = {};
    if (!container || !container.querySelectorAll) {
      return replyDrafts;
    }
    var existingThreads = container.querySelectorAll(".plan-comment-thread[data-comment-id]");
    for (var draftIndex = 0; draftIndex < existingThreads.length; draftIndex += 1) {
      var existingId = existingThreads[draftIndex].getAttribute("data-comment-id");
      var existingInput = existingThreads[draftIndex].querySelector(
        ".plan-comment-reply-form textarea"
      );
      if (existingId && existingInput && existingInput.value) {
        replyDrafts[existingId] = existingInput.value;
      }
    }
    return replyDrafts;
  }

  function mergeReplyDrafts(into, from) {
    if (!from) {
      return into;
    }
    Object.keys(from).forEach(function (id) {
      if (!into[id]) {
        into[id] = from[id];
      }
    });
    return into;
  }

  function clearManagedInlineThreadContainers(bodyEl) {
    if (!bodyEl || !bodyEl.querySelectorAll) {
      return;
    }
    var containers = bodyEl.querySelectorAll(".plan-inline-threads");
    for (var i = 0; i < containers.length; i += 1) {
      containers[i].remove();
    }
  }

  function blockLinesPresentInBody(bodyEl) {
    var map = {};
    if (!bodyEl || !bodyEl.querySelectorAll) {
      return map;
    }
    var blocks = bodyEl.querySelectorAll("[data-src-line]");
    for (var i = 0; i < blocks.length; i += 1) {
      var line = blocks[i].getAttribute("data-src-line");
      if (line != null && line !== "") {
        map[String(line)] = true;
      }
    }
    return map;
  }

  function placementsForRoots(roots, docBody, docSha) {
    var byId = {};
    var outdated = {};
    (roots || []).forEach(function (root) {
      if (root.line_start == null) {
        byId[root.id] = null;
        return;
      }
      var placement = placementForRootThread(root, docBody, docSha);
      byId[root.id] = placement;
      if (placement.outdated) {
        outdated[root.id] = true;
      }
    });
    return { byId: byId, outdated: outdated };
  }

  function partitionRootThreads(threads, docBody, docSha, availableBlockLines) {
    var inlineByBlock = {};
    var trayThreads = [];
    var roots = (threads || []).map(function (thread) {
      return thread.root;
    });
    var placementInfo = placementsForRoots(roots, docBody, docSha);
    (threads || []).forEach(function (thread) {
      var root = thread.root;
      var placement = placementInfo.byId[root.id];
      if (root.line_start != null && placement) {
        var blockLine = blockStartLineForSourceLine(docBody, placement.gutterLine);
        var key = String(blockLine);
        if (availableBlockLines && availableBlockLines[key]) {
          if (!inlineByBlock[key]) {
            inlineByBlock[key] = [];
          }
          inlineByBlock[key].push(thread);
          return;
        }
      }
      trayThreads.push(thread);
    });
    return {
      inlineByBlock: inlineByBlock,
      trayThreads: trayThreads,
      placementInfo: placementInfo,
    };
  }

  function clearPlanThreadGutters(bodyEl) {
    if (!bodyEl || !bodyEl.querySelectorAll) {
      return;
    }
    var markers = bodyEl.querySelectorAll(".plan-gutter-thread");
    for (var i = 0; i < markers.length; i += 1) {
      markers[i].remove();
    }
  }

  function applyPlanThreadGutters(bodyEl, body, roots, placementsById) {
    if (!bodyEl || !bodyEl.querySelectorAll) {
      return;
    }
    clearPlanThreadGutters(bodyEl);
    (roots || []).forEach(function (root) {
      var placement = placementsById && placementsById[root.id];
      if (!placement) {
        return;
      }
      var blockLine = blockStartLineForSourceLine(body, placement.gutterLine);
      var block = bodyEl.querySelector('[data-src-line="' + blockLine + '"]');
      if (!block) {
        return;
      }
      var marker = document.createElement("a");
      marker.className = "plan-gutter-thread";
      marker.setAttribute("data-comment-id", root.id);
      marker.href = "#plan-thread-" + encodeURIComponent(root.id);
      marker.setAttribute(
        "aria-label",
        placement.outdated ? "Open outdated review thread" : "Open review thread"
      );
      if (placement.outdated) {
        marker.classList.add("outdated");
      }
      marker.textContent = "●";
      block.appendChild(marker);
    });
  }

  function installPlanGutters(bodyEl, onAdd) {
    if (!bodyEl || !bodyEl.querySelectorAll) {
      return;
    }
    var blocks = bodyEl.querySelectorAll("[data-src-line]");
    for (var i = 0; i < blocks.length; i += 1) {
      var block = blocks[i];
      if (block.querySelector(".plan-gutter-add")) {
        continue;
      }
      var line = parseInt(block.getAttribute("data-src-line"), 10);
      if (!Number.isFinite(line)) {
        continue;
      }
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "plan-gutter-add";
      btn.textContent = "+";
      btn.setAttribute("aria-label", "Comment on source line " + line);
      btn.addEventListener("click", function (lineNum) {
        return function (ev) {
          ev.preventDefault();
          ev.stopPropagation();
          onAdd(lineNum);
        };
      }(line));
      block.insertBefore(btn, block.firstChild);
    }
  }

  function initPlanComments(workId, tier, options) {
    options = options || {};
    if (tier === "task") {
      if (options.testHooks) {
        return { skipped: true };
      }
      return;
    }
    var docBody = options.docBody != null ? String(options.docBody) : "";
    var docSha = options.docSha != null ? String(options.docSha) : "";
    var bodyEl = options.bodyEl || document.getElementById("plan-body");

    var panel = document.getElementById("plan-comments");
    var threadEl = document.getElementById("plan-comment-threads");
    var compose = document.getElementById("plan-comment-compose");
    var bodyInput = document.getElementById("plan-comment-body");
    var blockingInput = document.getElementById("plan-comment-blocking");
    var statusEl = document.getElementById("plan-comment-status");
    var composeHint = document.getElementById("plan-comment-compose-hint");
    var selectionBar = document.getElementById("plan-comment-selection-bar");
    var selectionBtn = document.getElementById("plan-comment-on-selection");
    if (!panel || !threadEl || !compose || !bodyInput) {
      return;
    }

    var selectionDraft = null;
    var activeInlineCompose = null;
    var lastCommentsSignature = null;

    function setCommentStatus(msg, isError) {
      if (!statusEl) return;
      statusEl.textContent = msg || "";
      statusEl.classList.toggle("error", !!isError);
    }

    function insertAfter(reference, node) {
      if (!reference || !reference.parentNode) return;
      reference.parentNode.insertBefore(node, reference.nextSibling);
    }

    function blockForSourceLine(line) {
      if (!bodyEl) return null;
      var blockLine = blockStartLineForSourceLine(docBody, line);
      return bodyEl.querySelector('[data-src-line="' + blockLine + '"]');
    }

    function removeInlineCompose(preserveViewport) {
      if (!activeInlineCompose) return;
      var x = window.scrollX || window.pageXOffset || 0;
      var y = window.scrollY || window.pageYOffset || 0;
      activeInlineCompose.remove();
      activeInlineCompose = null;
      if (preserveViewport && typeof window.scrollTo === "function") {
        window.scrollTo(x, y);
      }
    }

    function showInlineCompose(target) {
      var anchorBlock = target.anchorBlock || blockForSourceLine(target.line_start);
      if (!anchorBlock) return;
      removeInlineCompose(true);

      var form = document.createElement("form");
      form.className = "plan-comment-compose plan-inline-comment-compose";
      form.setAttribute("aria-label", "Comment on selected plan lines");

      var hint = document.createElement("p");
      hint.className = "plan-comment-compose-hint";
      hint.textContent =
        "Section " + target.section + " · lines " + target.line_start + "–" + target.line_end;

      var field = document.createElement("label");
      field.className = "plan-comment-field";
      field.appendChild(document.createTextNode("Comment"));
      var input = document.createElement("textarea");
      input.name = "body";
      input.rows = 4;
      input.required = true;
      input.setAttribute("aria-label", "Comment on lines " + target.line_start + "–" + target.line_end);
      field.appendChild(input);

      var blockingLabel = document.createElement("label");
      blockingLabel.className = "plan-comment-blocking blocking-toggle";
      var inlineBlocking = document.createElement("input");
      inlineBlocking.type = "checkbox";
      inlineBlocking.name = "blocking";
      blockingLabel.appendChild(inlineBlocking);
      blockingLabel.appendChild(document.createTextNode(" Blocking"));

      var actions = document.createElement("div");
      actions.className = "plan-inline-comment-actions";
      var submit = document.createElement("button");
      submit.type = "submit";
      submit.textContent = "Post comment";
      var cancel = document.createElement("button");
      cancel.type = "button";
      cancel.className = "plan-comment-compose-cancel";
      cancel.textContent = "Cancel";
      actions.appendChild(submit);
      actions.appendChild(cancel);

      var localStatus = document.createElement("p");
      localStatus.className = "plan-inline-comment-status";
      localStatus.setAttribute("role", "status");
      form.appendChild(hint);
      form.appendChild(field);
      form.appendChild(blockingLabel);
      form.appendChild(actions);
      form.appendChild(localStatus);
      insertAfter(anchorBlock, form);
      activeInlineCompose = form;

      cancel.addEventListener("click", function () {
        removeInlineCompose(true);
      });
      form.addEventListener("submit", function (ev) {
        ev.preventDefault();
        var text = input.value.trim();
        if (!text) {
          localStatus.textContent = "Comment is required.";
          localStatus.classList.add("error");
          return;
        }
        submit.disabled = true;
        localStatus.textContent = "Posting…";
        localStatus.classList.remove("error");
        postJsonComment(rootCommentPayload(workId, text, target, docSha, inlineBlocking.checked))
          .then(function (payload) {
            if (!payload || payload.ok !== true || !payload.comment_id) {
              throw new Error("Unexpected post response");
            }
            removeInlineCompose(false);
            return loadComments();
          })
          .catch(function (err) {
            localStatus.textContent = err && err.message ? err.message : "Post failed";
            localStatus.classList.add("error");
            submit.disabled = false;
          });
      });
      try {
        input.focus({ preventScroll: true });
      } catch (_err) {
        input.focus();
      }
      setCommentStatus("", false);
    }

    function beginRootFromLine(lineStart) {
      var lineEnd = lineEndForBlockStart(docBody, lineStart);
      showInlineCompose({
        line_start: lineStart,
        line_end: lineEnd,
        section: sectionForSourceLine(docBody, lineStart),
        anchor: snippetFromLines(docBody, lineStart, lineEnd, 120),
        anchorBlock: blockForSourceLine(lineStart),
      });
    }

    function beginRootFromSelection() {
      if (!selectionDraft) {
        return;
      }
      showInlineCompose(selectionDraft);
      if (selectionBar) {
        selectionBar.hidden = true;
      }
      selectionDraft = null;
    }

    function updateSelectionDraft() {
      if (!bodyEl || !selectionBar || !selectionBtn) {
        return;
      }
      var sel = window.getSelection();
      if (!sel || sel.isCollapsed || !sel.toString().trim()) {
        selectionDraft = null;
        selectionBar.hidden = true;
        return;
      }
      if (!bodyEl.contains(sel.anchorNode) || !bodyEl.contains(sel.focusNode)) {
        selectionDraft = null;
        selectionBar.hidden = true;
        return;
      }
      var startLine = srcLineFromDomNode(sel.anchorNode, bodyEl);
      var endLine = srcLineFromDomNode(sel.focusNode, bodyEl);
      if (startLine == null || endLine == null) {
        selectionDraft = null;
        selectionBar.hidden = true;
        return;
      }
      var lineStart = Math.min(startLine, endLine);
      var lineEnd = Math.max(
        lineEndForBlockStart(docBody, startLine),
        lineEndForBlockStart(docBody, endLine)
      );
      if (lineEnd < lineStart) {
        lineEnd = lineStart;
      }
      var anchor = sel.toString().trim();
      if (anchor.length > 120) {
        anchor = anchor.slice(0, 120);
      }
      selectionDraft = {
        line_start: lineStart,
        line_end: lineEnd,
        section: sectionForSourceLine(docBody, lineStart),
        anchor: anchor,
        anchorBlock: blockForSourceLine(lineStart),
      };
      if (selectionDraft.anchorBlock) {
        insertAfter(selectionDraft.anchorBlock, selectionBar);
      }
      selectionBar.hidden = false;
    }

    var commentNodes = new Map();
    function buildCommentNode(row, threadOutdated) {
      var signature = JSON.stringify([row, !!threadOutdated]);
      var cached = commentNodes.get(row.id);
      if (cached && cached.signature === signature) return cached.node;
      var wrap = document.createElement("div");
      wrap.className = "plan-comment-entry";
      wrap.setAttribute("data-entry-id", row.id);
      if (row.parent) wrap.setAttribute("data-parent-id", row.parent);
      var meta = document.createElement("div");
      meta.className = "plan-comment-meta";
      meta.textContent =
        (row.author || "unknown") +
        " · " +
        (row.section || "") +
        (row.parent ? " · reply to " + row.parent : "") +
        (row.blocking ? " · blocking" : "") +
        (threadOutdated ? " · outdated" : "") +
        (row.state === "resolved" ? " · resolved" : "");
      var body = document.createElement("p");
      body.className = "plan-comment-body-text";
      body.textContent = row.body || "";
      wrap.appendChild(meta);
      wrap.appendChild(body);
      commentNodes.set(row.id, { signature: signature, node: wrap });
      return wrap;
    }

    function buildReplyForm(rootId) {
      var form = document.createElement("form");
      form.className = "plan-comment-reply-form";
      var textarea = document.createElement("textarea");
      textarea.rows = 2;
      textarea.required = true;
      textarea.setAttribute("aria-label", "Reply");
      var submit = document.createElement("button");
      submit.type = "submit";
      submit.textContent = "Reply";
      form.appendChild(textarea);
      form.appendChild(submit);
      form.addEventListener("submit", function (ev) {
        ev.preventDefault();
        var text = textarea.value.trim();
        if (!text) {
          return;
        }
        submit.disabled = true;
        setCommentStatus("Posting reply…", false);
        fetch("/api/comment", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            doc_id: workId,
            body: text,
            parent: rootId,
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
              if (resp.status !== 202 && !resp.ok) {
                var errMsg =
                  payload && payload.error ? payload.error : "Post failed (" + resp.status + ")";
                throw new Error(errMsg);
              }
              return payload;
            });
          })
          .then(function (payload) {
            if (!payload || payload.ok !== true) {
              throw new Error("Unexpected reply response");
            }
            textarea.value = "";
            setCommentStatus("");
            return loadComments();
          })
          .catch(function (err) {
            setCommentStatus(err && err.message ? err.message : "Post failed", true);
          })
          .finally(function () {
            submit.disabled = false;
          });
      });
      return form;
    }

    function buildResolveControl(rootId) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "plan-comment-resolve";
      btn.textContent = "Resolve";
      btn.addEventListener("click", function (ev) {
        ev.preventDefault();
        btn.disabled = true;
        postResolveComment(rootId)
          .then(function () {
            return loadComments();
          })
          .catch(function (err) {
            setCommentStatus(err && err.message ? err.message : "Resolve failed", true);
          })
          .finally(function () {
            btn.disabled = false;
          });
      });
      return btn;
    }

    var threadBlocks = new Map();
    function buildThreadBlock(thread, placementInfo, preserved, replyDrafts) {
      var key = JSON.stringify([thread.root, !!placementInfo.outdated[thread.root.id]]);
      var cached = threadBlocks.get(thread.root.id);
      if (cached && cached.key === key) {
        var oldReplies = cached.block.querySelector(".plan-comment-replies");
        if (oldReplies) oldReplies.remove();
        var replies = document.createElement("div");
        replies.className = "plan-comment-replies";
        thread.replies.forEach(function (reply) { replies.appendChild(buildCommentNode(reply)); });
        cached.block.insertBefore(replies, cached.block.children[1] || null);
        return cached.block;
      }
      var root = thread.root;
      var block = document.createElement("div");
      block.className = "plan-comment-thread";
      if (root.state === "resolved") {
        block.classList.add("resolved");
      }
      if (placementInfo.outdated[root.id]) {
        block.classList.add("outdated");
      }
      block.setAttribute("role", "listitem");
      block.setAttribute("data-comment-id", root.id);
      block.id = "plan-thread-" + root.id;
      block.appendChild(buildCommentNode(root, !!placementInfo.outdated[root.id]));
      var replies = thread.replies;
      if (replies.length) {
        var replyWrap = document.createElement("div");
        replyWrap.className = "plan-comment-replies";
        replies.forEach(function (reply) {
          replyWrap.appendChild(buildCommentNode(reply));
        });
        block.appendChild(replyWrap);
      }
      if (root.state !== "resolved") {
        block.appendChild(buildResolveControl(root.id));
        var replyForm = buildReplyForm(root.id);
        var replyDraft = replyDrafts[root.id];
        if (replyDraft) {
          replyForm.querySelector("textarea").value = replyDraft;
        }
        block.appendChild(replyForm);
      }
      var extras = preserved[root.id];
      if (extras) {
        extras.forEach(function (node) {
          block.appendChild(node);
        });
      }
      threadBlocks.set(root.id, { key: key, block: block });
      return block;
    }

    function renderCommentThreads(comments) {
      var focused = document.activeElement;
      var scrollX = window.scrollX || 0;
      var scrollY = window.scrollY || 0;
      var preserved = collectPreservedThreadExtras(threadEl);
      if (bodyEl) {
        mergePreservedThreadExtras(preserved, collectPreservedThreadExtras(bodyEl));
      }
      var replyDrafts = collectReplyDrafts(threadEl);
      if (bodyEl) {
        mergeReplyDrafts(replyDrafts, collectReplyDrafts(bodyEl));
      }
      threadEl.innerHTML = "";
      if (bodyEl) {
        clearManagedInlineThreadContainers(bodyEl);
      }
      var threads = groupCommentThreads(comments).filter(function (thread) {
        // Typed diagram threads have their own semantic target renderer.  Keep
        // their replies with that root instead of duplicating the thread in the
        // heading/line/global plan-comment tray.
        return !thread.root.semantic_anchor;
      });
      var liveIds = new Set(comments.map(function (row) { return row.id; }));
      commentNodes.forEach(function (_value, id) { if (!liveIds.has(id)) commentNodes.delete(id); });
      var rootIds = new Set(threads.map(function (thread) { return thread.root.id; }));
      threadBlocks.forEach(function (_value, id) { if (!rootIds.has(id)) threadBlocks.delete(id); });
      var roots = threads.map(function (thread) {
        return thread.root;
      });
      var availableBlockLines = blockLinesPresentInBody(bodyEl);
      var partition = partitionRootThreads(threads, docBody, docSha, availableBlockLines);
      var placementInfo = partition.placementInfo;
      if (bodyEl) {
        applyPlanThreadGutters(bodyEl, docBody, roots, placementInfo.byId);
      }
      var renderedThreadIds = {};
      if (bodyEl) {
        var blockNodes = bodyEl.querySelectorAll("[data-src-line]");
        for (var blockIndex = 0; blockIndex < blockNodes.length; blockIndex += 1) {
          var blockNode = blockNodes[blockIndex];
          var lineKey = blockNode.getAttribute("data-src-line");
          var inlineGroup = lineKey != null ? partition.inlineByBlock[String(lineKey)] : null;
          if (!inlineGroup || !inlineGroup.length) {
            continue;
          }
          var inlineContainer = document.createElement("div");
          inlineContainer.className = "plan-inline-threads";
          inlineContainer.setAttribute("role", "list");
          inlineContainer.setAttribute("aria-label", "Review threads for this plan block");
          inlineGroup.forEach(function (thread) {
            if (renderedThreadIds[thread.root.id]) {
              return;
            }
            renderedThreadIds[thread.root.id] = true;
            inlineContainer.appendChild(
              buildThreadBlock(thread, placementInfo, preserved, replyDrafts)
            );
          });
          if (inlineContainer.childNodes.length) {
            insertAfter(blockNode, inlineContainer);
          }
        }
      }
      partition.trayThreads.forEach(function (thread) {
        if (renderedThreadIds[thread.root.id]) {
          return;
        }
        renderedThreadIds[thread.root.id] = true;
        threadEl.appendChild(
          buildThreadBlock(thread, placementInfo, preserved, replyDrafts)
        );
      });
      if (focused && focused.isConnected && typeof focused.focus === "function") {
        focused.focus({ preventScroll: true });
      }
      if (typeof window.scrollTo === "function") window.scrollTo(scrollX, scrollY);
    }

    function postResolveComment(commentId) {
      return fetch("/api/comment/resolve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ doc_id: workId, comment_id: commentId }),
      }).then(function (resp) {
        return resp.text().then(function (raw) {
          var payload;
          try {
            payload = JSON.parse(raw);
          } catch (_e) {
            payload = { error: raw };
          }
          if (resp.status !== 202 && !resp.ok) {
            throw new Error(payload && payload.error ? payload.error : "Resolve failed");
          }
          return payload;
        });
      });
    }

    var stopped = false;
    var refreshGeneration = 0;
    var refreshTimer = null;
    var requestTimer = null;
    var inFlight = null;
    var requestController = null;
    var retryDelay = 2000;
    var refreshStarted = false;
    var refreshOnSettle = false;
    var loadErrorShown = false;

    function canRefresh() {
      return !stopped && !document.hidden &&
        (typeof navigator === "undefined" || navigator.onLine !== false);
    }

    function clearRefreshTimer() {
      if (refreshTimer !== null) clearTimeout(refreshTimer);
      refreshTimer = null;
    }

    function scheduleRefresh() {
      clearRefreshTimer();
      if (refreshStarted && canRefresh()) {
        refreshTimer = setTimeout(function () {
          refreshTimer = null;
          loadComments().catch(function () {});
        }, retryDelay);
      }
    }

    function loadComments() {
      if (stopped) return Promise.resolve();
      if (inFlight) return inFlight;
      clearRefreshTimer();
      var generation = refreshGeneration;
      requestController = new AbortController();
      requestTimer = setTimeout(function () { requestController.abort(); }, 10000);
      inFlight = fetch("/api/comments/" + encodeURIComponent(workId), {
        signal: requestController.signal,
      })
        .then(function (resp) {
          if (!resp.ok) throw new Error("Failed to load comments (" + resp.status + ")");
          return resp.json();
        })
        .then(function (data) {
          if (stopped || generation !== refreshGeneration) return;
          var comments = data.comments || [];
          var signature = JSON.stringify(comments);
          if (signature !== lastCommentsSignature) {
            renderCommentThreads(comments);
            lastCommentsSignature = signature;
          }
          retryDelay = 2000;
          if (loadErrorShown) { setCommentStatus("", false); loadErrorShown = false; }
        })
        .catch(function (err) {
          if (stopped || generation !== refreshGeneration) return;
          if (!stopped && lastCommentsSignature === null) {
            setCommentStatus("Could not load comments; retrying…", true);
            loadErrorShown = true;
          }
          retryDelay = Math.min(retryDelay * 2, 30000);
          throw err;
        })
        .finally(function () {
          clearTimeout(requestTimer);
          requestTimer = null;
          requestController = null;
          inFlight = null;
          if (refreshOnSettle && canRefresh()) {
            refreshOnSettle = false;
            loadComments().catch(function () {});
          } else {
            scheduleRefresh();
          }
        });
      return inFlight;
    }

    function resumeRefresh() {
      clearRefreshTimer();
      if (canRefresh()) {
        // A read begun before reconnect/visibility may have an old snapshot.
        // Coalesce wake-ups into one fresh read once that request settles.
        if (inFlight) refreshOnSettle = true;
        else {
          refreshOnSettle = false;
          loadComments().catch(function () {});
        }
      }
    }

    function stopRefresh() {
      stopped = true;
      refreshGeneration += 1;
      refreshOnSettle = false;
      clearRefreshTimer();
      if (requestTimer !== null) clearTimeout(requestTimer);
      if (requestController) requestController.abort();
      document.removeEventListener("visibilitychange", resumeRefresh);
      window.removeEventListener("online", resumeRefresh);
      window.removeEventListener("offline", resumeRefresh);
      window.removeEventListener("pagehide", onPageHide);
    }

    function onPageHide(event) {
      stopRefresh();
      if (event.persisted) window.addEventListener("pageshow", startRefresh, { once: true });
    }

    function startRefresh() {
      stopped = false;
      refreshStarted = true;
      document.addEventListener("visibilitychange", resumeRefresh);
      window.addEventListener("online", resumeRefresh);
      window.addEventListener("offline", resumeRefresh);
      window.addEventListener("pagehide", onPageHide);
      resumeRefresh();
    }

    function postJsonComment(payload) {
      return fetch("/api/comment", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }).then(function (resp) {
        return resp.text().then(function (raw) {
          var parsed;
          try {
            parsed = JSON.parse(raw);
          } catch (_e) {
            parsed = { error: raw };
          }
          if (resp.status !== 202 && !resp.ok) {
            var errMsg =
              parsed && parsed.error ? parsed.error : "Post failed (" + resp.status + ")";
            throw new Error(errMsg);
          }
          return parsed;
        });
      });
    }

    compose.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var text = bodyInput.value.trim();
      if (!text) {
        setCommentStatus("Comment is required.", true);
        return;
      }
      setCommentStatus("Posting…", false);
      postJsonComment(
        rootCommentPayload(workId, text, null, docSha, blockingInput && blockingInput.checked)
      )
        .then(function (payload) {
          if (!payload || payload.ok !== true || !payload.comment_id) {
            throw new Error("Unexpected post response");
          }
          bodyInput.value = "";
          if (blockingInput) {
            blockingInput.checked = false;
          }
          setCommentStatus("", false);
          return loadComments();
        })
        .catch(function (err) {
          setCommentStatus(err && err.message ? err.message : "Post failed", true);
        });
    });

    if (selectionBtn) {
      selectionBtn.addEventListener("mousedown", function (ev) {
        // Keep the document selection intact until its saved draft is opened.
        ev.preventDefault();
      });
      selectionBtn.addEventListener("click", function () {
        beginRootFromSelection();
      });
    }
    if (bodyEl) {
      bodyEl.addEventListener("mouseup", function (ev) {
        if (selectionBar && selectionBar.contains(ev.target)) return;
        updateSelectionDraft();
      });
      installPlanGutters(bodyEl, beginRootFromLine);
    }

    if (options.testHooks) {
      return {
        renderComments: renderCommentThreads,
        loadComments: loadComments,
        startRefresh: startRefresh,
        stopRefresh: stopRefresh,
        getCommentStatus: function () {
          return statusEl ? statusEl.textContent : "";
        },
      };
    }

    panel.hidden = false;
    startRefresh();
  }

  function sortedDrillChoices(target) {
    var rows = Array.isArray(target && target.drill_choices) ? target.drill_choices.slice() : [];
    // Keep compatibility with review payloads produced before drill_choices was
    // introduced.  New projections always use the validated list.
    if (!rows.length && target && target.drill_view_key && target.drill_level) {
      rows.push({
        view_key: target.drill_view_key,
        level: target.drill_level,
        label: target.drill_view_key + " (" + target.drill_level + ")",
      });
    }
    return rows.filter(function (row) {
      return row && typeof row.view_key === "string" && row.view_key &&
        typeof row.level === "string" && row.level;
    }).sort(function (a, b) {
      var level = a.level.localeCompare(b.level);
      return level || a.view_key.localeCompare(b.view_key) ||
        String(a.label || "").localeCompare(String(b.label || ""));
    });
  }

  function createPairedNavigation(payload) {
    var views = Array.isArray(payload && payload.views) ? payload.views.slice() : [];
    var changed = Array.isArray(payload && payload.changed_views) ? payload.changed_views : [];

    function findView(viewKey, level) {
      return views.find(function (view) {
        return view.key === viewKey && view.level === level;
      }) || null;
    }

    var initial = null;
    if (changed.length) initial = findView(changed[0][0], changed[0][1]);
    if (!initial && views.length) initial = views[0];
    var state = initial ? {
      view_key: initial.key,
      level: initial.level,
      selection: null,
      history: [],
    } : { view_key: null, level: null, selection: null, history: [] };

    function snapshot() {
      return {
        view_key: state.view_key,
        level: state.level,
        selection: state.selection ? {
          kind: state.selection.kind,
          semantic_id: state.selection.semantic_id,
          source_side: state.selection.source_side,
        } : null,
      };
    }

    function currentView() {
      return findView(state.view_key, state.level);
    }

    function sideResolution(view, sideName, kind, semanticId) {
      var side = view && view[sideName];
      if (!side) return { state: "absent", side: sideName };
      if (side.interactive === false) {
        return { state: "unsupported", side: sideName, reason: side.error || "Interaction unsupported" };
      }
      var target = (side.targets || []).find(function (item) {
        return item.kind === kind && item.semantic_id === semanticId;
      });
      return target
        ? { state: "present", side: sideName, target: target }
        : { state: "absent", side: sideName };
    }

    function push(next) {
      state.history.push(snapshot());
      state.view_key = next.view_key;
      state.level = next.level;
      state.selection = next.selection || null;
      return snapshot();
    }

    return {
      state: state,
      views: views,
      currentView: currentView,
      resolutions: function () {
        if (!state.selection) return null;
        var view = currentView();
        return {
          current: sideResolution(
            view, "current", state.selection.kind, state.selection.semantic_id
          ),
          proposed: sideResolution(
            view, "proposed", state.selection.kind, state.selection.semantic_id
          ),
        };
      },
      select: function (kind, semanticId, sourceSide) {
        var view = currentView();
        if (!view || (kind !== "element" && kind !== "relationship") ||
            (sourceSide !== "current" && sourceSide !== "proposed")) {
          return { ok: false, error: "Unsupported paired diagram selection" };
        }
        var source = sideResolution(view, sourceSide, kind, semanticId);
        if (source.state !== "present") {
          return { ok: false, error: source.reason || "Target is not present in the selected side" };
        }
        push({
          view_key: view.key,
          level: view.level,
          selection: { kind: kind, semantic_id: semanticId, source_side: sourceSide },
        });
        return { ok: true, state: snapshot(), resolutions: this.resolutions() };
      },
      showView: function (viewKey, level) {
        var view = findView(viewKey, level);
        if (!view) return { ok: false, error: "Unknown paired diagram view" };
        push({ view_key: view.key, level: view.level, selection: null });
        return { ok: true, state: snapshot() };
      },
      drill: function (sourceSide, kind, semanticId) {
        var view = currentView();
        var resolution = sideResolution(view, sourceSide, kind, semanticId);
        var target = resolution.target;
        var choices = sortedDrillChoices(target);
        var requestedView = arguments.length > 3 ? arguments[3] : null;
        var requestedLevel = arguments.length > 4 ? arguments[4] : null;
        if (!choices.length) {
          return { ok: false, error: "No verified drill target is available" };
        }
        var choice = null;
        if (requestedView && requestedLevel) {
          choice = choices.find(function (row) {
            return row.view_key === requestedView && row.level === requestedLevel;
          }) || null;
          if (!choice) return { ok: false, error: "Verified drill choice is unavailable" };
        } else if (choices.length === 1) {
          choice = choices[0];
        } else {
          return {
            ok: false,
            needs_choice: true,
            error: "Choose a verified destination; this target appears in multiple views.",
            choices: choices,
          };
        }
        var destination = findView(choice.view_key, choice.level);
        if (!destination) return { ok: false, error: "Verified drill target is unavailable" };
        push({ view_key: destination.key, level: destination.level, selection: null });
        return { ok: true, state: snapshot() };
      },
      drillChoices: function (sourceSide, kind, semanticId) {
        var resolution = sideResolution(currentView(), sourceSide, kind, semanticId);
        return sortedDrillChoices(resolution.target);
      },
      back: function () {
        if (!state.history.length) return { ok: false, error: "No previous paired view" };
        var previous = state.history.pop();
        state.view_key = previous.view_key;
        state.level = previous.level;
        state.selection = previous.selection;
        return { ok: true, state: snapshot(), resolutions: this.resolutions() };
      },
      updatePayload: function (nextPayload) {
        views = Array.isArray(nextPayload && nextPayload.views) ? nextPayload.views.slice() : [];
        this.views = views;
        var surviving = findView(state.view_key, state.level);
        if (!surviving) {
          var nextChanged = Array.isArray(nextPayload && nextPayload.changed_views) ?
            nextPayload.changed_views : [];
          surviving = nextChanged.length ? findView(nextChanged[0][0], nextChanged[0][1]) : null;
          if (!surviving) surviving = views[0] || null;
          state.view_key = surviving ? surviving.key : null;
          state.level = surviving ? surviving.level : null;
          state.selection = null;
        } else if (state.selection && sideResolution(
          surviving,
          state.selection.source_side,
          state.selection.kind,
          state.selection.semantic_id
        ).state !== "present") {
          state.selection = null;
        }
        state.history = state.history.filter(function (entry) {
          return !!findView(entry.view_key, entry.level);
        });
        return { ok: true, state: snapshot(), resolutions: this.resolutions() };
      },
    };
  }

  function createSemanticThreadModel(payload, navigation, options) {
    options = options || {};
    var state = { threads: [], loading: false, error: null };

    function sideRecord(sideName) {
      return (payload.repositories || []).find(function (row) {
        return row.side === sideName;
      }) || null;
    }

    function repositoryFor(kind, sideName) {
      if (kind === "requirement") {
        var plan = payload.provenance && payload.provenance.plan;
        if (plan && plan.repository_key && plan.revision) return plan;
      }
      return sideRecord(sideName);
    }

    function sourceFor(kind, targetKey, sideName, viewKey, level) {
      if (kind === "requirement") {
        if ((payload.requirements || []).indexOf(targetKey) < 0) return null;
        return payload.diffs && payload.diffs.plan;
      }
      if (kind === "view") {
        var exactView = (payload.views || []).find(function (view) {
          return view.key === targetKey && view.level === level && view[sideName];
        });
        return exactView && exactView[sideName].svg;
      }
      if (kind !== "element" && kind !== "relationship") return null;
      var containing = (payload.views || []).find(function (view) {
        var side = view[sideName];
        return side && (side.targets || []).some(function (target) {
          return target.kind === kind && target.semantic_id === targetKey;
        });
      });
      return containing && containing[sideName].svg;
    }

    function buildAnchor(kind, targetKey, sideName, viewKey, level) {
      var repository = repositoryFor(kind, sideName);
      var source = sourceFor(kind, targetKey, sideName, viewKey, level);
      var diff = payload.diffs && payload.diffs.source;
      if (!repository || !source || typeof diff !== "string" || !diff) {
        return null;
      }
      return {
        version: 1,
        kind: kind,
        target_key: targetKey,
        view_key: kind === "view" ? targetKey : null,
        level: kind === "view" ? level : null,
        source_side: sideName,
        repository_key: repository.repository_key,
        revision: repository.revision,
        review_unit_id: payload.review_unit_id,
        reviewed_tuple_digest: payload.reviewed_tuple_digest,
        original_source_reference: source,
        original_diff_link: diff,
      };
    }

    function reviewedReplacement(anchor) {
      if (anchor.kind !== "element" && anchor.kind !== "relationship") return null;
      var identities = payload.diffs && payload.diffs.model && payload.diffs.model.identities;
      var replacement = (Array.isArray(identities) ? identities : []).find(function (row) {
        return row.kind === anchor.kind &&
          row.previous_semantic_id === anchor.target_key &&
          sourceFor(anchor.kind, row.semantic_id, anchor.source_side, null, null);
      });
      return replacement ? replacement.semantic_id : null;
    }

    function freshnessFor(anchor) {
      var repository = repositoryFor(anchor.kind, anchor.source_side);
      if (!repository) return ["outdated", "source_side_missing"];
      if (repository.repository_key !== anchor.repository_key) {
        return ["outdated", "repository_mismatch"];
      }
      if (repository.revision !== anchor.revision) {
        return ["outdated", "revision_mismatch"];
      }
      if (sourceFor(
        anchor.kind, anchor.target_key, anchor.source_side,
        anchor.view_key, anchor.level
      )) return ["current", null];
      if (reviewedReplacement(anchor)) return ["current", null];
      return ["outdated", "target_missing_or_renamed"];
    }

    function normalize(row) {
      var anchor = row && (row.anchor || row.semantic_anchor);
      if (!anchor || row.parent) return null;
      var resolved = freshnessFor(anchor);
      return {
        id: row.id,
        body: row.body,
        author: row.author,
        state: row.state === "resolved" ? "resolved" : "open",
        blocking: row.blocking === true,
        anchor: anchor,
        freshness: row.freshness === "outdated" ? "outdated" : resolved[0],
        outdated_reason: row.freshness === "outdated" ?
          (row.outdated_reason || resolved[1]) : resolved[1],
      };
    }

    function load() {
      state.loading = true;
      state.error = null;
      var request;
      if (Array.isArray(payload.semantic_threads)) {
        request = Promise.resolve(payload.semantic_threads);
      } else if (options.loadThreads) {
        request = Promise.resolve(options.loadThreads(payload));
      } else {
        request = fetch("/api/comments/" + encodeURIComponent(payload.owner_work_id), {
          signal: pageLoadSignal(),
        }).then(function (response) {
          if (!response.ok) throw new Error("Failed to load semantic threads (" + response.status + ")");
          return response.json();
        }).then(function (value) { return value.comments || []; });
      }
      return request.then(function (rows) {
        state.threads = (rows || []).map(normalize).filter(Boolean);
        state.loading = false;
        return state.threads;
      }).catch(function (error) {
        state.loading = false;
        state.error = error && error.message ? error.message : "Failed to load semantic threads";
        return state.threads;
      });
    }

    function create(anchor, body, blocking) {
      var request = {
        doc_id: payload.owner_work_id,
        section: "semantic-review",
        body: body,
        blocking: blocking === true,
        semantic_anchor: anchor,
      };
      if (options.createThread) return Promise.resolve(options.createThread(request));
      return fetch("/api/comment", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      }).then(function (response) {
        return response.json().then(function (value) {
          if (!response.ok || !value.ok) throw new Error(value.error || "Failed to post semantic thread");
          return value;
        });
      });
    }

    function navigate(thread) {
      if (!thread || thread.freshness !== "current") {
        return { ok: false, error: "Outdated targets retain their original links but cannot be selected." };
      }
      var anchor = thread.anchor;
      if (anchor.kind === "requirement") {
        return { ok: true, requirement: anchor.target_key };
      }
      if (anchor.kind === "view") {
        return navigation.showView(anchor.target_key, anchor.level);
      }
      var navigationTarget = sourceFor(
        anchor.kind, anchor.target_key, anchor.source_side, null, null
      ) ? anchor.target_key : reviewedReplacement(anchor);
      if (!navigationTarget) {
        return { ok: false, error: "Semantic target is no longer available." };
      }
      var location = (payload.views || []).find(function (view) {
        var side = view[anchor.source_side];
        return side && (side.targets || []).some(function (target) {
          return target.kind === anchor.kind && target.semantic_id === navigationTarget;
        });
      });
      if (!location) return { ok: false, error: "Semantic target is no longer available." };
      var moved = navigation.showView(location.key, location.level);
      if (!moved.ok) return moved;
      return navigation.select(anchor.kind, navigationTarget, anchor.source_side);
    }

    return {
      state: state,
      buildAnchor: buildAnchor,
      normalize: normalize,
      load: load,
      create: create,
      navigate: navigate,
    };
  }

  /**
   * Render one revision-pinned semantic C4 view.
   *
   * Pair coordination deliberately lives outside this primitive so the branch
   * architecture tab can use the same verified SVG binding, target list and
   * viewport behavior without pretending it has a counterpart.
   */
  function createSemanticC4Viewer(options) {
    options = options || {};
    var doc = options.document || document;
    var container = options.container;
    var side = options.side;
    var sideName = options.sideName || "view";
    var destroyed = false;
    var svg = null;
    var bound = {};
    var originalViewBox = null;
    var currentViewBox = null;
    var drag = null;

    if (!container) throw new Error("A semantic C4 viewer container is required");

    function element(tag, className, text) {
      var value = doc.createElement(tag);
      value.className = className || "";
      if (text != null) value.textContent = String(text);
      return value;
    }

    function announce(message, isError) {
      if (options.status) {
        options.status.textContent = message || "";
        options.status.classList.toggle("error", !!isError);
      }
    }

    function parseViewBox(value) {
      var parts = String(value || "").trim().split(/[ ,]+/).map(Number);
      return parts.length === 4 && parts.every(Number.isFinite) &&
        parts[2] > 0 && parts[3] > 0 ? parts : null;
    }

    function setViewBox(box) {
      if (!svg || !box) return;
      currentViewBox = box.slice();
      svg.setAttribute("viewBox", currentViewBox.join(" "));
    }

    function fit() {
      if (originalViewBox) setViewBox(originalViewBox);
    }

    function zoom(factor) {
      if (!currentViewBox || !Number.isFinite(factor) || factor <= 0) return;
      var nextWidth = currentViewBox[2] / factor;
      var nextHeight = currentViewBox[3] / factor;
      var next = [
        currentViewBox[0] + (currentViewBox[2] - nextWidth) / 2,
        currentViewBox[1] + (currentViewBox[3] - nextHeight) / 2,
        nextWidth,
        nextHeight,
      ];
      setViewBox(next);
    }

    function targetKey(kind, semanticId) {
      return kind + "\u0000" + semanticId;
    }

    function targetLabel(target) {
      return target.label || target.semantic_id;
    }

    function emitSelection(target, source) {
      var detail = {
        kind: target.kind,
        semantic_id: target.semantic_id,
        side: sideName,
        target: target,
        source: source,
      };
      if (typeof options.onSelect === "function") options.onSelect(detail);
      if (container.dispatchEvent && typeof CustomEvent !== "undefined") {
        container.dispatchEvent(new CustomEvent("cascade:c4-selection", {
          bubbles: true,
          detail: detail,
        }));
      }
    }

    function emitDrill(target) {
      if (typeof options.onDrill === "function") {
        options.onDrill({
          kind: target.kind,
          semantic_id: target.semantic_id,
          side: sideName,
          target: target,
          choices: sortedDrillChoices(target),
        });
      }
    }

    function applyTargetState(hit, target) {
      hit.classList.add("semantic-c4-target", "paired-c4-target");
      hit.classList.add("semantic-c4-diff-" + (target.state || "unchanged"));
      hit.setAttribute("data-cascade-diff-state", target.state || "unchanged");
      hit.setAttribute("tabindex", "0");
      hit.setAttribute("role", "button");
      hit.setAttribute("aria-label", target.kind + " " + target.semantic_id);
      hit.setAttribute("aria-description", targetLabel(target) + ", " +
        (target.state || "unchanged"));
      var selected = options.selection &&
        options.selection.kind === target.kind &&
        options.selection.semantic_id === target.semantic_id;
      if (selected) {
        hit.classList.add("semantic-c4-target-selected", "paired-c4-target-selected");
        hit.setAttribute("aria-pressed", "true");
      } else {
        hit.setAttribute("aria-pressed", "false");
      }
      function choose(event) {
        if (event && event.type === "click" && event.detail > 1) return;
        emitSelection(target, "svg");
      }
      hit.addEventListener("click", choose);
      hit.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          choose(event);
        }
      });
      if (sortedDrillChoices(target).length) {
        hit.addEventListener("dblclick", function (event) {
          event.preventDefault();
          emitDrill(target);
        });
      }
    }

    function loadSvg() {
      if (!side || typeof side.svg !== "string" || !side.svg.trim()) {
        return Promise.reject(new Error("Pinned diagram SVG is unavailable"));
      }
      if (side.svg.trim().charAt(0) === "<") return Promise.resolve(side.svg);
      var loader = options.loadSvg || function (url) {
        return fetch(url, { signal: pageLoadSignal() }).then(function (response) {
          if (!response.ok) throw new Error("Failed to load pinned diagram (" + response.status + ")");
          return response.text();
        });
      };
      return Promise.resolve(loader(side.svg));
    }

    function install(raw) {
      var Parser = options.DOMParser ||
        (doc.defaultView && doc.defaultView.DOMParser) ||
        (typeof DOMParser !== "undefined" ? DOMParser : null);
      if (!Parser) throw new Error("SVG parsing is unavailable");
      var parsed = new Parser().parseFromString(raw, "image/svg+xml");
      if (parsed.querySelector("parsererror, script, foreignObject, iframe, object, embed")) {
        throw new Error("Pinned diagram SVG failed safety validation");
      }
      var parsedSvg = parsed.documentElement;
      if (!parsedSvg || String(parsedSvg.localName).toLowerCase() !== "svg") {
        throw new Error("Pinned diagram is not an SVG");
      }
      svg = doc.importNode ? doc.importNode(parsedSvg, true) : parsedSvg;
      svg.classList.add("semantic-c4-svg", "paired-c4-svg");
      svg.setAttribute("role", "group");
      svg.setAttribute("aria-label", sideName + " semantic architecture diagram");
      var annotated = svg.querySelectorAll("[data-cascade-semantic-id]");
      for (var i = 0; i < annotated.length; i += 1) {
        var semanticId = annotated[i].getAttribute("data-cascade-semantic-id");
        var kind = annotated[i].getAttribute("data-cascade-model-kind");
        var key = targetKey(kind, semanticId);
        if (bound[key]) throw new Error("Diagram contains an ambiguous semantic hit target");
        bound[key] = annotated[i];
      }
      (side.targets || []).forEach(function (target) {
        var hit = bound[targetKey(target.kind, target.semantic_id)];
        if (!hit) throw new Error("Diagram is missing a verified semantic hit target");
        applyTargetState(hit, target);
      });
      originalViewBox = parseViewBox(svg.getAttribute("viewBox"));
      if (!originalViewBox) {
        var width = parseFloat(svg.getAttribute("width"));
        var height = parseFloat(svg.getAttribute("height"));
        if (width > 0 && height > 0) originalViewBox = [0, 0, width, height];
      }
      if (originalViewBox) setViewBox(originalViewBox);
      canvas.replaceChildren ? canvas.replaceChildren(svg) : (canvas.innerHTML = "", canvas.appendChild(svg));

      svg.addEventListener("wheel", function (event) {
        if (!event.ctrlKey && !event.metaKey) return;
        event.preventDefault();
        zoom(event.deltaY < 0 ? 1.2 : 1 / 1.2);
      }, { passive: false });
      svg.addEventListener("pointerdown", function (event) {
        if (!currentViewBox || event.button !== 0 || event.target.closest(".semantic-c4-target")) return;
        drag = { x: event.clientX, y: event.clientY, box: currentViewBox.slice() };
        if (svg.setPointerCapture) svg.setPointerCapture(event.pointerId);
        svg.classList.add("semantic-c4-panning");
      });
      svg.addEventListener("pointermove", function (event) {
        if (!drag || !svg.clientWidth || !svg.clientHeight) return;
        setViewBox([
          drag.box[0] - (event.clientX - drag.x) * drag.box[2] / svg.clientWidth,
          drag.box[1] - (event.clientY - drag.y) * drag.box[3] / svg.clientHeight,
          drag.box[2], drag.box[3],
        ]);
      });
      function endPan() {
        drag = null;
        svg.classList.remove("semantic-c4-panning");
      }
      svg.addEventListener("pointerup", endPan);
      svg.addEventListener("pointercancel", endPan);
      var selected = options.selection && bound[targetKey(
        options.selection.kind, options.selection.semantic_id
      )];
      if (selected && options.selection.source_side === sideName && selected.focus) {
        try { selected.focus({ preventScroll: true }); } catch (_err) { selected.focus(); }
      }
      return api;
    }

    var toolbar = element("div", "semantic-c4-toolbar");
    [["Zoom out", function () { zoom(1 / 1.2); }],
      ["Zoom in", function () { zoom(1.2); }],
      ["Fit", fit]].forEach(function (row) {
      var button = element("button", "semantic-c4-viewport-control", row[0]);
      button.type = "button";
      button.addEventListener("click", row[1]);
      toolbar.appendChild(button);
    });
    container.appendChild(toolbar);
    var canvas = element("div", "semantic-c4-canvas paired-c4-canvas");
    canvas.setAttribute("aria-label", sideName + " diagram");
    canvas.appendChild(element("p", "paired-c4-loading", "Loading pinned diagram…"));
    container.appendChild(canvas);

    var semanticList = element("details", "semantic-c4-targets");
    semanticList.appendChild(element("summary", "", "Semantic targets (" +
      ((side && side.targets && side.targets.length) || 0) + ")"));
    var list = element("ul", "semantic-c4-target-list");
    (side && side.targets || []).forEach(function (target) {
      var item = element("li", "semantic-c4-target-row semantic-c4-diff-" +
        (target.state || "unchanged"));
      var select = element("button", "semantic-c4-target-button",
        target.kind + ": " + targetLabel(target) + " · " + (target.state || "unchanged"));
      select.type = "button";
      select.addEventListener("click", function () { emitSelection(target, "list"); });
      item.appendChild(select);
      if (target.kind === "relationship" && (target.source || target.destination)) {
        item.appendChild(element("span", "semantic-c4-relationship-details",
          " " + (target.source || "?") + " → " + (target.destination || "?")));
      }
      var choices = sortedDrillChoices(target);
      if (choices.length) {
        var drill = element("button", "semantic-c4-drill", choices.length === 1 ?
          "Open " + (choices[0].label || choices[0].view_key) :
          "Choose destination (" + choices.length + ")");
        drill.type = "button";
        drill.title = choices.length === 1 ? "Open the verified containing view" :
          "This target is present in multiple verified views";
        drill.addEventListener("click", function () { emitDrill(target); });
        item.appendChild(drill);
      }
      list.appendChild(item);
    });
    semanticList.appendChild(list);
    container.appendChild(semanticList);

    var api = {
      ready: loadSvg().then(install).catch(function (error) {
        if (destroyed) return api;
        canvas.replaceChildren ? canvas.replaceChildren() : (canvas.innerHTML = "");
        canvas.appendChild(element("p", "paired-c4-unsupported",
          "Interaction unsupported: " + error.message));
        announce("Diagram interaction is unavailable; inspect the source diff below.", true);
        return api;
      }),
      fit: fit,
      zoomIn: function () { zoom(1.2); },
      zoomOut: function () { zoom(1 / 1.2); },
      focusTarget: function (kind, semanticId) {
        var hit = bound[targetKey(kind, semanticId)];
        if (hit && hit.focus) hit.focus();
        return !!hit;
      },
      getViewBox: function () { return currentViewBox && currentViewBox.slice(); },
      destroy: function () { destroyed = true; drag = null; },
    };
    return api;
  }

  function initPairedC4Review(payload, options) {
    options = options || {};
    var doc = options.document || document;
    var host = options.host || doc.getElementById("paired-c4-review");
    if (!host || !payload) return null;
    var navigation = createPairedNavigation(payload);
    var threadModel = createSemanticThreadModel(payload, navigation, options);
    var pendingAnchor = null;
    var pendingDrill = null;
    var pendingThreadDraft = "";
    var pendingThreadBlocking = false;
    var refreshTimer = null;
    var refreshInFlight = false;
    var stopped = false;
    host.hidden = false;

    function node(tag, className, text) {
      var el = doc.createElement(tag);
      el.className = className || "";
      if (text != null) el.textContent = String(text);
      return el;
    }

    function clear(element) {
      if (element.replaceChildren) element.replaceChildren();
      else element.innerHTML = "";
    }

    function appendReferences(parent, heading, values) {
      var rows = Array.isArray(values) ? values : [];
      if (!rows.length) return;
      var group = node("div", "paired-c4-reference-group");
      group.appendChild(node("strong", "", heading + ": "));
      rows.forEach(function (value, index) {
        if (index) group.appendChild(node("span", "", ", "));
        var reference = node("span", heading === "Requirements" ?
          "paired-c4-requirement" : "paired-c4-reference", value);
        if (heading === "Requirements") {
          reference.setAttribute("data-requirement-id", value);
          reference.setAttribute("tabindex", "-1");
        }
        group.appendChild(reference);
      });
      parent.appendChild(group);
    }

    function appendDiffs(parent) {
      var details = node("details", "paired-c4-diffs");
      details.appendChild(node("summary", "", "Reviewed diffs"));
      var list = node("dl", "paired-c4-diff-list");
      ["source", "model", "plan"].forEach(function (name) {
        var value = payload.diffs && payload.diffs[name];
        if (value == null) return;
        list.appendChild(node("dt", "", name));
        list.appendChild(node(
          "dd", "paired-c4-diff-value",
          typeof value === "string" ? value : JSON.stringify(value, null, 2)
        ));
      });
      details.appendChild(list);
      var resources = payload.diffs && payload.diffs.resources;
      if (Array.isArray(resources) && resources.length) {
        var links = node("ul", "paired-c4-resource-links");
        resources.forEach(function (resource) {
          var item = node("li", "");
          appendLink(
            item,
            "paired-c4-resource-link",
            "Open pinned " + (resource.kind || "diff"),
            resource.url
          );
          links.appendChild(item);
        });
        details.appendChild(links);
      }
      parent.appendChild(details);
    }

    function appendResources(parent) {
      if (!Array.isArray(payload.resources) || !payload.resources.length) return;
      var details = node("details", "paired-c4-resources");
      details.appendChild(node("summary", "", "Pinned readable resources"));
      var links = node("ul", "paired-c4-resource-links");
      payload.resources.forEach(function (resource) {
        var item = node("li", "");
        var label = "Open " + (resource.kind || "resource");
        if (resource.side) label += " (" + resource.side + ")";
        if (resource.path) label += " — " + resource.path;
        appendLink(item, "paired-c4-resource-link", label, resource.url);
        links.appendChild(item);
      });
      details.appendChild(links);
      parent.appendChild(details);
    }

    function appendLink(parent, className, label, href) {
      var url = safeUrl(href);
      if (!url) {
        parent.appendChild(node("span", className, label + ": " + href));
        return;
      }
      var link = node("a", className, label);
      link.href = url;
      parent.appendChild(link);
    }

    function beginThread(anchor) {
      pendingAnchor = anchor;
      render();
    }

    function anchorButton(parent, label, anchor) {
      if (!anchor) return;
      var button = node("button", "paired-c4-comment-target", label);
      button.type = "button";
      button.addEventListener("click", function () { beginThread(anchor); });
      parent.appendChild(button);
    }

    function renderThreadPanel() {
      var panel = node("section", "paired-c4-threads");
      panel.appendChild(node("h3", "paired-c4-threads-heading", "Semantic review threads"));

      var shortcuts = node("div", "paired-c4-thread-shortcuts");
      var view = navigation.currentView();
      (payload.requirements || []).forEach(function (requirement) {
        ["current", "proposed"].forEach(function (sideName) {
          var anchor = threadModel.buildAnchor("requirement", requirement, sideName, null, null);
          anchorButton(shortcuts, "Comment on " + requirement + " (" + sideName + ")", anchor);
        });
      });
      if (view) {
        ["current", "proposed"].forEach(function (sideName) {
          anchorButton(
            shortcuts,
            "Comment on " + sideName + " view",
            threadModel.buildAnchor("view", view.key, sideName, view.key, view.level)
          );
        });
      }
      var selection = navigation.state.selection;
      if (selection) {
        anchorButton(
          shortcuts,
          "Comment on selected " + selection.kind,
          threadModel.buildAnchor(
            selection.kind, selection.semantic_id, selection.source_side, null, null
          )
        );
      }
      panel.appendChild(shortcuts);

      if (pendingAnchor) {
        var form = node("form", "paired-c4-thread-compose");
        form.appendChild(node(
          "p", "paired-c4-thread-target",
          pendingAnchor.kind + " " + pendingAnchor.target_key + " · " +
            pendingAnchor.repository_key + " @ " + pendingAnchor.revision
        ));
        var body = node("textarea", "paired-c4-thread-body");
        body.rows = 3;
        body.required = true;
        body.value = pendingThreadDraft;
        body.setAttribute("aria-label", "Semantic comment");
        body.addEventListener("input", function () { pendingThreadDraft = body.value; });
        form.appendChild(body);
        var blockingLabel = node("label", "paired-c4-thread-blocking", " Blocking");
        var blocking = node("input", "");
        blocking.type = "checkbox";
        blocking.checked = pendingThreadBlocking;
        blocking.addEventListener("change", function () {
          pendingThreadBlocking = blocking.checked;
        });
        blockingLabel.insertBefore(blocking, blockingLabel.children[0] || null);
        form.appendChild(blockingLabel);
        var send = node("button", "", "Post thread");
        send.type = "submit";
        form.appendChild(send);
        var cancel = node("button", "", "Cancel");
        cancel.type = "button";
        cancel.addEventListener("click", function () {
          pendingAnchor = null;
          pendingThreadDraft = "";
          pendingThreadBlocking = false;
          render();
        });
        form.appendChild(cancel);
        form.addEventListener("submit", function (event) {
          event.preventDefault();
          var text = String(body.value || "").trim();
          if (!text) return;
          send.disabled = true;
          threadModel.create(pendingAnchor, text, blocking.checked).then(function () {
            pendingAnchor = null;
            pendingThreadDraft = "";
            pendingThreadBlocking = false;
            return threadModel.load();
          }).then(render).catch(function (error) {
            send.disabled = false;
            threadModel.state.error = error.message || "Failed to post semantic thread";
            render();
          });
        });
        panel.appendChild(form);
      }

      if (threadModel.state.error) {
        panel.appendChild(node("p", "paired-c4-thread-error", threadModel.state.error));
      }
      var list = node("div", "paired-c4-thread-list");
      threadModel.state.threads.forEach(function (thread) {
        var item = node("article", "paired-c4-thread paired-c4-thread-" + thread.freshness);
        item.setAttribute("data-thread-id", thread.id || "");
        var anchor = thread.anchor;
        item.appendChild(node(
          "h4", "paired-c4-thread-title",
          anchor.kind + " " + anchor.target_key
        ));
        item.appendChild(node(
          "p", "paired-c4-thread-state",
          thread.state + (thread.blocking ? " · blocking" : " · non-blocking") +
            " · " + thread.freshness
        ));
        if (thread.freshness === "outdated") {
          item.appendChild(node(
            "p", "paired-c4-thread-outdated",
            "Outdated: " + (thread.outdated_reason || "target is no longer current")
          ));
        }
        item.appendChild(node("p", "paired-c4-thread-body-text", thread.body));
        item.appendChild(node(
          "p", "paired-c4-thread-revision",
          anchor.source_side + " · " + anchor.repository_key + " @ " + anchor.revision
        ));
        var links = node("p", "paired-c4-thread-links");
        appendLink(links, "paired-c4-thread-source", "Original source", anchor.original_source_reference);
        links.appendChild(node("span", "", " · "));
        appendLink(links, "paired-c4-thread-diff", "Original diff", anchor.original_diff_link);
        item.appendChild(links);
        if (thread.freshness === "current") {
          var open = node("button", "paired-c4-thread-open", "Open target");
          open.type = "button";
          open.addEventListener("click", function () {
            var result = threadModel.navigate(thread);
            if (result.ok) {
              render();
              if (result.requirement && host.querySelectorAll) {
                var requirement = Array.prototype.find.call(
                  host.querySelectorAll("[data-requirement-id]"),
                  function (item) {
                    return item.getAttribute("data-requirement-id") === result.requirement;
                  }
                );
                if (requirement) {
                  requirement.classList.add("paired-c4-requirement-selected");
                  if (requirement.focus) requirement.focus();
                }
              }
            }
          });
          item.appendChild(open);
        }
        list.appendChild(item);
      });
      if (!threadModel.state.loading && !threadModel.state.threads.length) {
        list.appendChild(node("p", "paired-c4-thread-empty", "No semantic threads yet."));
      }
      panel.appendChild(list);
      host.appendChild(panel);
    }

    function renderSide(parent, view, sideName, status) {
      var side = view[sideName];
      var card = node("section", "paired-c4-side paired-c4-side-" + sideName);
      card.setAttribute("data-side", sideName);
      card.appendChild(node("h3", "paired-c4-side-heading", sideName === "current" ? "Current" : "Proposed"));
      if (!side) {
        card.classList.add("paired-c4-side-absent");
        card.appendChild(node("p", "paired-c4-absent", "Absent counterpart for this view."));
        parent.appendChild(card);
        return;
      }
      card.appendChild(node(
        "p", "paired-c4-revision",
        side.repository_key + " @ " + side.revision
      ));
      var selectedResolutions = navigation.resolutions();
      var selectedResolution = selectedResolutions && selectedResolutions[sideName];
      if (selectedResolution && selectedResolution.state === "absent") {
        card.appendChild(node(
          "p", "paired-c4-absent",
          "Selected semantic target has no " + sideName + " counterpart."
        ));
      }
      var viewerHost = node("div", "semantic-c4-viewer");
      card.appendChild(viewerHost);
      parent.appendChild(card);
      createSemanticC4Viewer({
        document: doc,
        container: viewerHost,
        side: side,
        sideName: sideName,
        selection: navigation.state.selection,
        status: status,
        loadSvg: options.loadSvg,
        DOMParser: options.DOMParser,
        onSelect: function (detail) {
          var result = navigation.select(detail.kind, detail.semantic_id, sideName);
          if (!result.ok) {
            status.textContent = result.error;
            status.classList.add("error");
            return;
          }
          pendingDrill = null;
          if (typeof options.onSelection === "function") {
            options.onSelection(detail, result);
          }
          render();
        },
        onDrill: function (detail) {
          if (detail.choices.length === 1) {
            var choice = detail.choices[0];
            var moved = navigation.drill(
              sideName, detail.kind, detail.semantic_id, choice.view_key, choice.level
            );
            if (moved.ok) {
              pendingDrill = null;
              render();
            }
            return;
          }
          pendingDrill = detail;
          render();
        },
      });
    }

    function render() {
      clear(host);
      var heading = node("div", "paired-c4-heading");
      var title = node("div", "");
      title.appendChild(node("h2", "", "Architecture change review"));
      title.appendChild(node("p", "paired-c4-summary", payload.summary || "No semantic summary supplied."));
      heading.appendChild(title);
      host.appendChild(heading);
      var status = node("p", "paired-c4-status");
      status.setAttribute("role", "status");
      host.appendChild(status);

      if (payload.state === "error") {
        host.appendChild(node("p", "paired-c4-error", payload.error || "Paired diagram review is unavailable."));
        appendDiffs(host);
        renderThreadPanel();
        return;
      }
      if (!navigation.views.length) {
        host.appendChild(node(
          "p", "paired-c4-empty",
          payload.state === "unchanged" ? "No diagram changes." : "No paired diagram views are available (" + payload.state + ")."
        ));
        appendDiffs(host);
        renderThreadPanel();
        return;
      }

      var controls = node("div", "paired-c4-controls");
      var back = node("button", "paired-c4-back", "Back");
      back.type = "button";
      back.disabled = navigation.state.history.length === 0;
      back.addEventListener("click", function () {
        if (navigation.back().ok) render();
      });
      controls.appendChild(back);
      var label = node("label", "paired-c4-view-label", "View ");
      var select = node("select", "paired-c4-view-select");
      navigation.views.forEach(function (view) {
        var option = node("option", "", view.key + " · " + view.level + " · " + view.state);
        option.value = view.key + "\u0000" + view.level;
        option.setAttribute("data-view-state", view.state || "unchanged");
        option.setAttribute("data-changed", view.state !== "unchanged" ? "true" : "false");
        option.selected = view.key === navigation.state.view_key && view.level === navigation.state.level;
        select.appendChild(option);
      });
      select.addEventListener("change", function () {
        var parts = select.value.split("\u0000");
        if (navigation.showView(parts[0], parts[1]).ok) render();
      });
      label.appendChild(select);
      controls.appendChild(label);
      host.appendChild(controls);

      if (pendingDrill) {
        var chooser = node("div", "paired-c4-drill-choices");
        chooser.appendChild(node(
          "p", "paired-c4-drill-explanation",
          "Choose a verified destination. This semantic target occurs in multiple views."
        ));
        pendingDrill.choices.forEach(function (choice) {
          var choiceButton = node(
            "button", "paired-c4-drill-choice",
            choice.label || choice.view_key + " (" + choice.level + ")"
          );
          choiceButton.type = "button";
          choiceButton.addEventListener("click", function () {
            var result = navigation.drill(
              pendingDrill.side,
              pendingDrill.kind,
              pendingDrill.semantic_id,
              choice.view_key,
              choice.level
            );
            if (result.ok) {
              pendingDrill = null;
              render();
            }
          });
          chooser.appendChild(choiceButton);
        });
        var cancelDrill = node("button", "paired-c4-drill-cancel", "Cancel");
        cancelDrill.type = "button";
        cancelDrill.addEventListener("click", function () { pendingDrill = null; render(); });
        chooser.appendChild(cancelDrill);
        host.appendChild(chooser);
      }

      var view = navigation.currentView();
      var diagrams = node("div", "paired-c4-diagrams");
      renderSide(diagrams, view, "current", status);
      renderSide(diagrams, view, "proposed", status);
      host.appendChild(diagrams);

      var resolutions = navigation.resolutions();
      if (resolutions) {
        var selection = navigation.state.selection;
        status.textContent = selection.kind + " " + selection.semantic_id +
          " — current: " + resolutions.current.state +
          ", proposed: " + resolutions.proposed.state;
        status.classList.toggle(
          "paired-c4-status-absent",
          resolutions.current.state === "absent" || resolutions.proposed.state === "absent"
        );
      }
      var meta = node("div", "paired-c4-review-meta");
      appendReferences(meta, "Requirements", payload.requirements);
      appendReferences(meta, "Decisions", payload.decisions);
      var legend = node("ul", "paired-c4-legend");
      (payload.legend || []).forEach(function (item) {
        legend.appendChild(node("li", "paired-c4-legend-" + item.state, item.state + ": " + item.meaning));
      });
      if (legend.children.length) meta.appendChild(legend);
      appendResources(meta);
      appendDiffs(meta);
      host.appendChild(meta);
      renderThreadPanel();
    }

    render();
    threadModel.load().then(render);
    function scheduleRefresh() {
      if (stopped || typeof options.refreshPayload !== "function") return;
      if (refreshTimer !== null) clearTimeout(refreshTimer);
      refreshTimer = setTimeout(refresh, Math.max(5000, options.refreshIntervalMs || 15000));
    }
    function refresh() {
      if (stopped || refreshInFlight || typeof options.refreshPayload !== "function") {
        scheduleRefresh();
        return Promise.resolve(null);
      }
      if (doc.hidden === true) {
        scheduleRefresh();
        return Promise.resolve(null);
      }
      refreshInFlight = true;
      return Promise.resolve(options.refreshPayload()).then(function (nextPayload) {
        if (!nextPayload || stopped) return null;
        // Preserve the object identity captured by the semantic-thread model.
        Object.keys(payload).forEach(function (key) { delete payload[key]; });
        Object.keys(nextPayload).forEach(function (key) { payload[key] = nextPayload[key]; });
        navigation.updatePayload(payload);
        return threadModel.load().then(function () {
          render();
          return nextPayload;
        });
      }).catch(function (error) {
        // Keep the last verified page usable while exposing a bounded refresh
        // failure.  The next active-page interval retries.
        threadModel.state.error = error && error.message ? error.message :
          "Failed to refresh architecture review";
        render();
        return null;
      }).finally(function () {
        refreshInFlight = false;
        scheduleRefresh();
      });
    }
    function stopRefresh() {
      stopped = true;
      if (refreshTimer !== null) clearTimeout(refreshTimer);
      refreshTimer = null;
    }
    scheduleRefresh();
    return {
      navigation: navigation,
      threads: threadModel,
      render: render,
      refresh: refresh,
      stopRefresh: stopRefresh,
      selection: function () { return navigation.state.selection; },
    };
  }

  function loadArchitectureReview(resourceUrl, options) {
    options = options || {};
    var maxPages = options.maxPages || 20;
    var limit = options.limit || 25;
    var pages = 0;
    var projection = null;
    var views = [];

    function pageUrl(cursor) {
      var separator = resourceUrl.indexOf("?") === -1 ? "?" : "&";
      return resourceUrl + separator + "cursor=" + cursor + "&limit=" + limit;
    }

    function load(cursor) {
      if (pages >= maxPages) {
        return Promise.reject(new Error("Architecture review exceeds the bounded page limit"));
      }
      pages += 1;
      return fetch(pageUrl(cursor), { signal: pageLoadSignal() }).then(function (response) {
        if (!response.ok) {
          throw new Error("Failed to load architecture review (" + response.status + ")");
        }
        return response.json();
      }).then(function (page) {
        if (!projection) projection = page;
        views = views.concat(Array.isArray(page.views) ? page.views : []);
        var next = page.pagination && page.pagination.next_cursor;
        return next == null ? projection : load(next);
      });
    }

    return load(0).then(function () {
      projection.views = views;
      return projection;
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
          if (doc.paired_review) {
            var envelope = doc.paired_review;
            if (envelope.resource_url) {
              loadArchitectureReview(envelope.resource_url)
                .then(function (review) {
                  initPairedC4Review(review, {
                    refreshPayload: function () {
                      return loadArchitectureReview(envelope.resource_url);
                    },
                    refreshIntervalMs: envelope.retry && envelope.retry.retry_after_seconds ?
                      envelope.retry.retry_after_seconds * 1000 : 15000,
                  });
                })
                .catch(function (error) {
                  initPairedC4Review({
                    state: "error",
                    summary: envelope.message || "Architecture review is unavailable.",
                    error: (envelope.message || error.message || "Architecture review is unavailable.") +
                      (envelope.retry && envelope.retry.retryable ? " Retry shortly." : ""),
                    views: [], changed_views: [], diffs: {},
                  });
                });
            } else {
              initPairedC4Review(envelope);
            }
          }
          var readinessMount = null;
          if (meta.tier === "epic" && doc.plan_readiness) {
            readinessMount = initEpicPlanReadinessChrome(workId, doc.plan_readiness);
          }
          if (meta.tier === "epic" && meta.dependency_status) {
            initDependencyReviewChrome(
              workId,
              meta.dependency_status,
              readinessMount
            );
          }
          initPlanComments(workId, meta.tier, {
            bodyEl: bodyEl,
            docBody: doc.body,
            docSha: doc.sha,
          });
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
    blockSourceRangesForBody: blockSourceRangesForBody,
    sectionSlug: sectionSlug,
    sectionForSourceLine: sectionForSourceLine,
    lineRangeForSectionSlug: lineRangeForSectionSlug,
    isSectionThread: isSectionThread,
    findAnchorLineInRange: findAnchorLineInRange,
    placementForRootThread: placementForRootThread,
    blockStartLineForSourceLine: blockStartLineForSourceLine,
    rootCommentPayload: rootCommentPayload,
    groupCommentThreads: groupCommentThreads,
    partitionRootThreads: partitionRootThreads,
    placementsForRoots: placementsForRoots,
    blockLinesPresentInBody: blockLinesPresentInBody,
    clearManagedInlineThreadContainers: clearManagedInlineThreadContainers,
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
    initPlanComments: initPlanComments,
    initEpicPlanReadinessChrome: initEpicPlanReadinessChrome,
    initDependencyReviewChrome: initDependencyReviewChrome,
    sortedDrillChoices: sortedDrillChoices,
    createSemanticC4Viewer: createSemanticC4Viewer,
    loadArchitectureReview: loadArchitectureReview,
    createPairedNavigation: createPairedNavigation,
    createSemanticThreadModel: createSemanticThreadModel,
    initPairedC4Review: initPairedC4Review,
  };
});

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
    var rows = comments || [];
    var repliesByParent = {};
    rows.forEach(function (row) {
      if (!row.parent) return;
      if (!repliesByParent[row.parent]) {
        repliesByParent[row.parent] = [];
      }
      repliesByParent[row.parent].push(row);
    });
    return rows
      .filter(function (row) {
        return !row.parent;
      })
      .map(function (root) {
        return { root: root, replies: repliesByParent[root.id] || [] };
      });
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

    function buildCommentNode(row, threadOutdated) {
      var wrap = document.createElement("div");
      wrap.className = "plan-comment-entry";
      var meta = document.createElement("div");
      meta.className = "plan-comment-meta";
      meta.textContent =
        (row.author || "unknown") +
        " · " +
        (row.section || "") +
        (row.blocking ? " · blocking" : "") +
        (threadOutdated ? " · outdated" : "") +
        (row.state === "resolved" ? " · resolved" : "");
      var body = document.createElement("p");
      body.className = "plan-comment-body-text";
      body.textContent = row.body || "";
      wrap.appendChild(meta);
      wrap.appendChild(body);
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

    function buildThreadBlock(thread, placementInfo, preserved, replyDrafts) {
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
      return block;
    }

    function renderCommentThreads(comments) {
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
      var threads = groupCommentThreads(comments);
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
          var comments = data.comments || [];
          var signature = JSON.stringify(comments);
          if (signature !== lastCommentsSignature) {
            lastCommentsSignature = signature;
            renderCommentThreads(comments);
          }
        });
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
        getCommentStatus: function () {
          return statusEl ? statusEl.textContent : "";
        },
      };
    }

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
  };
});

(() => {
  const root = document.querySelector(".reader-wrap[data-chapter-path]");
  if (!root) {
    return;
  }

  const normalizeText = (value) =>
    (value || "")
      .replace(/[\s\u3000]+/gu, " ")
      .trim();

  const readerContent = root.querySelector(".reader-content");

  const collectTranslatorNotes = (container) => {
    if (!container) {
      return { notes: new Map(), definitionElements: new WeakSet() };
    }

    const notes = new Map();
    const definitionElements = new WeakSet();
    const definitionMatcher = /^\[(\d+)\]\s*(?:[-–—:]\s*)?(.+)$/u;
    const blocks = container.querySelectorAll("p, li");

    for (const block of blocks) {
      const text = normalizeText(block.textContent || "");
      const match = text.match(definitionMatcher);
      if (!match) {
        continue;
      }
      notes.set(match[1], match[2].trim());
      definitionElements.add(block);
    }

    return { notes, definitionElements };
  };

  const replaceInlineTranslatorRefs = (container, notes, definitionElements) => {
    if (!container || !notes.size) {
      return;
    }

    const markerMatcher = /\[(\d+)\]/gu;
    const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
    const textNodes = [];

    while (walker.nextNode()) {
      textNodes.push(walker.currentNode);
    }

    for (const textNode of textNodes) {
      const parent = textNode.parentElement;
      if (!parent) {
        continue;
      }

      if (parent.closest("pre, code, a, script, style")) {
        continue;
      }

      if (parent.closest("p, li") && definitionElements.has(parent.closest("p, li"))) {
        continue;
      }

      const text = textNode.nodeValue || "";
      if (!markerMatcher.test(text)) {
        markerMatcher.lastIndex = 0;
        continue;
      }
      markerMatcher.lastIndex = 0;

      const fragment = document.createDocumentFragment();
      let lastIndex = 0;
      let changed = false;
      let match = markerMatcher.exec(text);
      while (match) {
        const [full, noteNumber] = match;
        const start = match.index;

        if (start > lastIndex) {
          fragment.appendChild(document.createTextNode(text.slice(lastIndex, start)));
        }

        const noteText = notes.get(noteNumber);
        if (noteText) {
          const marker = document.createElement("sup");
          marker.className = "tnote-ref";
          marker.textContent = full;
          marker.setAttribute("tabindex", "0");
          marker.setAttribute("aria-label", `Translator note ${noteNumber}: ${noteText}`);
          marker.dataset.noteText = noteText;
          fragment.appendChild(marker);
          changed = true;
        } else {
          fragment.appendChild(document.createTextNode(full));
        }

        lastIndex = start + full.length;
        match = markerMatcher.exec(text);
      }

      if (lastIndex < text.length) {
        fragment.appendChild(document.createTextNode(text.slice(lastIndex)));
      }

      if (changed) {
        textNode.parentNode.replaceChild(fragment, textNode);
      }
    }
  };

  const { notes: translatorNotes, definitionElements } = collectTranslatorNotes(readerContent);
  replaceInlineTranslatorRefs(readerContent, translatorNotes, definitionElements);

  const rulerTrack = document.querySelector("[data-ruler-track]");
  const rulerZone = document.querySelector("[data-ruler-zone]");
  const leftHandle = document.querySelector('[data-ruler-handle="left"]');
  const rightHandle = document.querySelector('[data-ruler-handle="right"]');
  const widthValue = document.querySelector("[data-reader-width-value]");
  const fontTrack = document.querySelector("[data-font-track]");
  const fontRail = document.querySelector("[data-font-rail]");
  const fontFill = document.querySelector("[data-font-fill]");
  const fontHandle = document.querySelector("[data-font-handle]");
  const fontValue = document.querySelector("[data-reader-font-value]");
  const contrastRail = document.querySelector("[data-contrast-rail]");
  const contrastFill = document.querySelector("[data-contrast-fill]");
  const contrastHandle = document.querySelector("[data-contrast-handle]");
  const contrastValue = document.querySelector("[data-reader-contrast-value]");
  const widthStorageKey = "rezeror:reader-width";
  const fontStorageKey = "rezeror:reader-font-size";
  const contrastStorageKey = "rezeror:reader-text-contrast";
  const minWidth = 620;
  const maxWidth = 1100;
  const widthStep = 20;
  const minFontSize = 14;
  const maxFontSize = 24;
  const fontStep = 0.5;
  const minContrast = 70;
  const maxContrast = 115;
  const contrastStep = 2;
  let currentWidth = 900;
  let currentFontSize = 16.5;
  let currentContrast = 74;

  const formatFontSize = (value) => {
    if (Number.isInteger(value)) {
      return String(value);
    }
    return value.toFixed(1).replace(/\.0$/, "");
  };

  const contrastStops = [
    { value: minContrast, color: [184, 177, 165] },
    { value: 100, color: [242, 240, 233] },
    { value: maxContrast, color: [255, 250, 242] },
  ];

  const interpolateChannel = (from, to, progress) => from + (to - from) * progress;

  const colorForContrast = (value) => {
    for (let i = 0; i < contrastStops.length - 1; i += 1) {
      const start = contrastStops[i];
      const end = contrastStops[i + 1];
      if (value <= end.value) {
        const progress = (value - start.value) / (end.value - start.value || 1);
        const rgb = start.color.map((channel, index) =>
          Math.round(interpolateChannel(channel, end.color[index], progress))
        );
        return `rgb(${rgb[0]} ${rgb[1]} ${rgb[2]})`;
      }
    }

    const fallback = contrastStops[contrastStops.length - 1].color;
    return `rgb(${fallback[0]} ${fallback[1]} ${fallback[2]})`;
  };

  const updateRulerUI = () => {
    if (!rulerTrack) {
      return;
    }
    const trackWidth = rulerTrack.getBoundingClientRect().width;
    if (trackWidth === 0) {
      return;
    }
    const margin = Math.max(0, (trackWidth - currentWidth) / 2);
    const leftPct = (margin / trackWidth) * 100;
    const rightPct = ((trackWidth - margin) / trackWidth) * 100;
    if (leftHandle) {
      leftHandle.style.left = `${leftPct}%`;
      leftHandle.setAttribute("aria-valuenow", String(currentWidth));
    }
    if (rightHandle) {
      rightHandle.style.left = `${rightPct}%`;
      rightHandle.setAttribute("aria-valuenow", String(currentWidth));
    }
    if (rulerZone) {
      rulerZone.style.left = `${leftPct}%`;
      rulerZone.style.width = `${rightPct - leftPct}%`;
    }
    if (widthValue) {
      widthValue.textContent = `${currentWidth}px`;
    }
  };

  const applyReaderWidth = (rawValue, save) => {
    const numeric = Number(rawValue);
    if (!Number.isFinite(numeric)) {
      return;
    }
    currentWidth = Math.min(maxWidth, Math.max(minWidth, Math.round(numeric / widthStep) * widthStep));
    document.documentElement.style.setProperty("--reader-content-width", `${currentWidth}px`);
    updateRulerUI();
    if (save) {
      try {
        window.localStorage.setItem(widthStorageKey, String(currentWidth));
      } catch (_) {}
    }
  };

  const updateFontUI = () => {
    if (!fontRail || !fontHandle) {
      return;
    }

    const railRect = fontRail.getBoundingClientRect();
    if (railRect.width === 0) {
      return;
    }

    const progress = (currentFontSize - minFontSize) / (maxFontSize - minFontSize);
    const handleLeft = railRect.width * progress;

    fontHandle.style.left = `${handleLeft}px`;
    const formattedFontSize = formatFontSize(currentFontSize);
    fontHandle.setAttribute("aria-valuenow", String(currentFontSize));
    fontHandle.setAttribute("aria-valuetext", `${formattedFontSize} pixels`);

    if (fontFill) {
      fontFill.style.width = `${handleLeft}px`;
    }

    if (fontValue) {
      fontValue.textContent = `${formattedFontSize}px`;
    }
  };

  const applyReaderFontSize = (rawValue, save) => {
    const numeric = Number(rawValue);
    if (!Number.isFinite(numeric)) {
      return;
    }

    currentFontSize = Math.min(
      maxFontSize,
      Math.max(minFontSize, Math.round(numeric / fontStep) * fontStep)
    );
    document.documentElement.style.setProperty("--reader-font-size", `${currentFontSize}px`);
    updateFontUI();
    if (save) {
      try {
        window.localStorage.setItem(fontStorageKey, String(currentFontSize));
      } catch (_) {}
    }
  };

  const updateContrastUI = () => {
    if (!contrastRail || !contrastHandle) {
      return;
    }

    const railRect = contrastRail.getBoundingClientRect();
    if (railRect.width === 0) {
      return;
    }

    const progress = (currentContrast - minContrast) / (maxContrast - minContrast);
    const handleLeft = railRect.width * progress;

    contrastHandle.style.left = `${handleLeft}px`;
    contrastHandle.setAttribute("aria-valuenow", String(currentContrast));
    contrastHandle.setAttribute("aria-valuetext", `${currentContrast} percent`);

    if (contrastFill) {
      contrastFill.style.width = `${handleLeft}px`;
    }

    if (contrastValue) {
      contrastValue.textContent = `${currentContrast}%`;
    }
  };

  const applyReaderContrast = (rawValue, save) => {
    const numeric = Number(rawValue);
    if (!Number.isFinite(numeric)) {
      return;
    }

    currentContrast = Math.min(
      maxContrast,
      Math.max(minContrast, Math.round(numeric / contrastStep) * contrastStep)
    );
    document.documentElement.style.setProperty("--reader-text-color", colorForContrast(currentContrast));
    updateContrastUI();
    if (save) {
      try {
        window.localStorage.setItem(contrastStorageKey, String(currentContrast));
      } catch (_) {}
    }
  };

  try {
    applyReaderWidth(window.localStorage.getItem(widthStorageKey) || 900, false);
  } catch (_) {
    applyReaderWidth(900, false);
  }

  try {
    applyReaderFontSize(window.localStorage.getItem(fontStorageKey) || 16.5, false);
  } catch (_) {
    applyReaderFontSize(16.5, false);
  }

  try {
    applyReaderContrast(window.localStorage.getItem(contrastStorageKey) || 74, false);
  } catch (_) {
    applyReaderContrast(74, false);
  }

  const makeHandleDraggable = (handle, side) => {
    if (!handle || !rulerTrack) {
      return;
    }
    const onMove = (clientX) => {
      const rect = rulerTrack.getBoundingClientRect();
      const relX = clientX - rect.left;
      const margin = side === "left" ? relX : rect.width - relX;
      applyReaderWidth(rect.width - 2 * margin, true);
    };
    const onMouseMove = (e) => onMove(e.clientX);
    const onMouseUp = () => {
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
    };
    handle.addEventListener("mousedown", (e) => {
      e.preventDefault();
      document.addEventListener("mousemove", onMouseMove);
      document.addEventListener("mouseup", onMouseUp);
    });
    const onTouchMove = (e) => {
      e.preventDefault();
      onMove(e.touches[0].clientX);
    };
    const onTouchEnd = () => {
      document.removeEventListener("touchmove", onTouchMove);
      document.removeEventListener("touchend", onTouchEnd);
    };
    handle.addEventListener("touchstart", (e) => {
      e.preventDefault();
      document.addEventListener("touchmove", onTouchMove, { passive: false });
      document.addEventListener("touchend", onTouchEnd);
    });
    handle.addEventListener("keydown", (e) => {
      if (e.key === "ArrowRight") {
        applyReaderWidth(currentWidth + widthStep, true);
        e.preventDefault();
      } else if (e.key === "ArrowLeft") {
        applyReaderWidth(currentWidth - widthStep, true);
        e.preventDefault();
      }
    });
  };

  makeHandleDraggable(leftHandle, "left");
  makeHandleDraggable(rightHandle, "right");

  if (fontRail && fontHandle) {
    const positionToFontSize = (clientX) => {
      const rect = fontRail.getBoundingClientRect();
      if (rect.width === 0) {
        return;
      }

      const clampedX = Math.min(rect.width, Math.max(0, clientX - rect.left));
      const progress = clampedX / rect.width;
      const fontSize = minFontSize + progress * (maxFontSize - minFontSize);
      applyReaderFontSize(fontSize, true);
    };

    const onMouseMove = (e) => positionToFontSize(e.clientX);
    const onMouseUp = () => {
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
    };
    fontHandle.addEventListener("mousedown", (e) => {
      e.preventDefault();
      document.addEventListener("mousemove", onMouseMove);
      document.addEventListener("mouseup", onMouseUp);
    });

    const onTouchMove = (e) => {
      e.preventDefault();
      positionToFontSize(e.touches[0].clientX);
    };
    const onTouchEnd = () => {
      document.removeEventListener("touchmove", onTouchMove);
      document.removeEventListener("touchend", onTouchEnd);
    };
    fontHandle.addEventListener("touchstart", (e) => {
      e.preventDefault();
      document.addEventListener("touchmove", onTouchMove, { passive: false });
      document.addEventListener("touchend", onTouchEnd);
    });

    fontRail.addEventListener("mousedown", (e) => {
      positionToFontSize(e.clientX);
    });

    fontHandle.addEventListener("keydown", (e) => {
      if (e.key === "ArrowRight") {
        applyReaderFontSize(currentFontSize + fontStep, true);
        e.preventDefault();
      } else if (e.key === "ArrowLeft") {
        applyReaderFontSize(currentFontSize - fontStep, true);
        e.preventDefault();
      } else if (e.key === "Home") {
        applyReaderFontSize(minFontSize, true);
        e.preventDefault();
      } else if (e.key === "End") {
        applyReaderFontSize(maxFontSize, true);
        e.preventDefault();
      }
    });

    new ResizeObserver(updateFontUI).observe(fontRail);
  }

  if (contrastRail && contrastHandle) {
    const positionToContrast = (clientX) => {
      const rect = contrastRail.getBoundingClientRect();
      if (rect.width === 0) {
        return;
      }

      const clampedX = Math.min(rect.width, Math.max(0, clientX - rect.left));
      const progress = clampedX / rect.width;
      const contrast = minContrast + progress * (maxContrast - minContrast);
      applyReaderContrast(contrast, true);
    };

    const onMouseMove = (e) => positionToContrast(e.clientX);
    const onMouseUp = () => {
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
    };
    contrastHandle.addEventListener("mousedown", (e) => {
      e.preventDefault();
      document.addEventListener("mousemove", onMouseMove);
      document.addEventListener("mouseup", onMouseUp);
    });

    const onTouchMove = (e) => {
      e.preventDefault();
      positionToContrast(e.touches[0].clientX);
    };
    const onTouchEnd = () => {
      document.removeEventListener("touchmove", onTouchMove);
      document.removeEventListener("touchend", onTouchEnd);
    };
    contrastHandle.addEventListener("touchstart", (e) => {
      e.preventDefault();
      document.addEventListener("touchmove", onTouchMove, { passive: false });
      document.addEventListener("touchend", onTouchEnd);
    });

    contrastRail.addEventListener("mousedown", (e) => {
      positionToContrast(e.clientX);
    });

    contrastHandle.addEventListener("keydown", (e) => {
      if (e.key === "ArrowRight") {
        applyReaderContrast(currentContrast + contrastStep, true);
        e.preventDefault();
      } else if (e.key === "ArrowLeft") {
        applyReaderContrast(currentContrast - contrastStep, true);
        e.preventDefault();
      } else if (e.key === "Home") {
        applyReaderContrast(minContrast, true);
        e.preventDefault();
      } else if (e.key === "End") {
        applyReaderContrast(maxContrast, true);
        e.preventDefault();
      }
    });

    new ResizeObserver(updateContrastUI).observe(contrastRail);
  }

  if (rulerTrack) {
    new ResizeObserver(updateRulerUI).observe(rulerTrack);
  }

  const chapterPath = root.getAttribute("data-chapter-path");
  const initialScroll = Number(root.getAttribute("data-saved-scroll") || "0");
  const rawHasSavedProgress = (root.getAttribute("data-has-saved-progress") || "").toLowerCase();
  const hasSavedProgress = rawHasSavedProgress === "1" || rawHasSavedProgress === "true";
  const rawOwnerAuthenticated = (root.getAttribute("data-owner-authenticated") || "").toLowerCase();
  const ownerAuthenticated = rawOwnerAuthenticated === "1" || rawOwnerAuthenticated === "true";

  const isSeparatorLike = (rawText) => {
    const compact = (rawText || "").replace(/[\s\u3000]+/gu, "");
    if (compact.length < 6) {
      return false;
    }

    const chars = Array.from(compact);
    const symbolCount = chars.filter((char) => /[\p{P}\p{S}]/u.test(char)).length;
    const uniqueCount = new Set(chars).size;
    const symbolRatio = symbolCount / chars.length;

    return symbolRatio >= 0.8 && uniqueCount <= 5;
  };

  const looksLikeCreditLine = (rawText) => {
    const text = normalizeText(rawText).toLowerCase();
    if (!text) {
      return true;
    }

    const markers = [
      "translated by",
      "edited by",
      "proofread",
      "all rights",
      "original author",
      "japanese web novel source",
      "source:",
      "disclaimer",
    ];

    return markers.some((marker) => text.includes(marker));
  };

  const looksNarrativeLike = (el) => {
    if (!el) {
      return false;
    }

    const text = normalizeText(el.textContent || "");
    if (!text || isSeparatorLike(text) || looksLikeCreditLine(text)) {
      return false;
    }

    const letters = text.match(/\p{L}/gu) || [];
    const lower = text.match(/\p{Ll}/gu) || [];
    const hasSentencePunctuation = /[.!?…]$|[.!?…]["'”’)]/u.test(text);

    if (letters.length < 8 || lower.length < 3) {
      return false;
    }

    if (text.length >= 40) {
      return true;
    }

    return text.length >= 18 && hasSentencePunctuation;
  };

  const findAutoStartElement = () => {
    const content = root.querySelector(".reader-content");
    if (!content) {
      return null;
    }

    const blocks = Array.from(content.querySelectorAll("p, li, blockquote, h2, h3, h4, h5, h6"));
    if (!blocks.length) {
      return null;
    }

    const separatorSearchLimit = Math.min(blocks.length, 45);
    let firstSeparator = -1;
    let lastSeparator = -1;
    let separatorCount = 0;

    for (let i = 0; i < separatorSearchLimit; i += 1) {
      if (isSeparatorLike(normalizeText(blocks[i].textContent || ""))) {
        if (firstSeparator === -1) {
          firstSeparator = i;
        }
        lastSeparator = i;
        separatorCount += 1;
      }
    }

    if (firstSeparator === -1 || firstSeparator > 20 || separatorCount < 2) {
      return null;
    }

    const narrativeScanStart = lastSeparator + 1;
    const narrativeScanEnd = Math.min(blocks.length, narrativeScanStart + 80);

    for (let i = narrativeScanStart; i < narrativeScanEnd; i += 1) {
      if (looksNarrativeLike(blocks[i])) {
        return blocks[i];
      }
    }

    return null;
  };

  const computeTopOffset = () => {
    const stickyHeader = document.querySelector(".site-header");
    const stickyHeight = stickyHeader ? Math.ceil(stickyHeader.getBoundingClientRect().height) : 0;
    return stickyHeight + 12;
  };

  if (hasSavedProgress) {
    if (initialScroll > 0) {
      window.requestAnimationFrame(() => {
        window.scrollTo({ top: initialScroll, behavior: "auto" });
      });
    }
  } else {
    const autoStartElement = findAutoStartElement();
    if (autoStartElement) {
      window.requestAnimationFrame(() => {
        const top = Math.max(
          0,
          Math.floor(autoStartElement.getBoundingClientRect().top + window.scrollY - computeTopOffset())
        );
        window.scrollTo({ top, behavior: "auto" });
        // Mark chapter as initialized even when user leaves quickly after opening.
        if (ownerAuthenticated) {
          window.setTimeout(() => {
            persist();
          }, 0);
        }
      });
    }
  }

  let saveTimer = null;

  const csrfToken = (document.querySelector("meta[name='csrf-token']") || {}).content || "";

  const persist = () => {
    if (!ownerAuthenticated) {
      return;
    }

    const payload = {
      chapter_path: chapterPath,
      scroll_y: Math.max(0, Math.floor(window.scrollY || 0)),
    };

    fetch("/api/progress", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken,
      },
      body: JSON.stringify(payload),
      keepalive: true,
    }).catch(() => {});
  };

  if (ownerAuthenticated) {
    window.addEventListener("scroll", () => {
      if (saveTimer) {
        clearTimeout(saveTimer);
      }
      saveTimer = window.setTimeout(persist, 250);
    });

    window.addEventListener("beforeunload", persist);
  }
})();

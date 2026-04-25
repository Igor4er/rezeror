(() => {
  const root = document.querySelector(".reader-wrap[data-chapter-path]");
  if (!root) {
    return;
  }

  const widthSlider = document.querySelector("[data-reader-width-slider]");
  const widthValue = document.querySelector("[data-reader-width-value]");
  const widthStorageKey = "rezeror:reader-width";
  const minWidth = 620;
  const maxWidth = 1100;

  const applyReaderWidth = (rawValue) => {
    const numeric = Number(rawValue);
    if (!Number.isFinite(numeric)) {
      return;
    }
    const bounded = Math.min(maxWidth, Math.max(minWidth, Math.round(numeric)));
    document.documentElement.style.setProperty("--reader-content-width", `${bounded}px`);
    if (widthSlider) {
      widthSlider.value = String(bounded);
    }
    if (widthValue) {
      widthValue.textContent = `${bounded}px`;
    }
  };

  try {
    const savedWidth = window.localStorage.getItem(widthStorageKey);
    if (savedWidth) {
      applyReaderWidth(savedWidth);
    } else if (widthSlider) {
      applyReaderWidth(widthSlider.value);
    }
  } catch (_) {
    if (widthSlider) {
      applyReaderWidth(widthSlider.value);
    }
  }

  if (widthSlider) {
    widthSlider.addEventListener("input", () => {
      applyReaderWidth(widthSlider.value);
      try {
        window.localStorage.setItem(widthStorageKey, widthSlider.value);
      } catch (_) {}
    });
  }

  const chapterPath = root.getAttribute("data-chapter-path");
  const initialScroll = Number(root.getAttribute("data-saved-scroll") || "0");
  const rawHasSavedProgress = (root.getAttribute("data-has-saved-progress") || "").toLowerCase();
  const hasSavedProgress = rawHasSavedProgress === "1" || rawHasSavedProgress === "true";

  const normalizeText = (value) =>
    (value || "")
      .replace(/[\s\u3000]+/gu, " ")
      .trim();

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
        window.setTimeout(() => {
          persist();
        }, 0);
      });
    }
  }

  let saveTimer = null;

  const persist = () => {
    const payload = {
      chapter_path: chapterPath,
      scroll_y: Math.max(0, Math.floor(window.scrollY || 0)),
    };

    fetch("/api/progress", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      keepalive: true,
    }).catch(() => {});
  };

  window.addEventListener("scroll", () => {
    if (saveTimer) {
      clearTimeout(saveTimer);
    }
    saveTimer = window.setTimeout(persist, 250);
  });

  window.addEventListener("beforeunload", persist);
})();

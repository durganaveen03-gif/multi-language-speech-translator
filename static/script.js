document.addEventListener("DOMContentLoaded", () => {
  const $ = (id) => document.getElementById(id);

  const speechInput = $("speech");
  const resultBox = $("result");
  const fromLang = $("from_lang");
  const toLang = $("to_lang");
  const translateBtn = $("translate");
  const recordBtn = $("record");
  const listenBtn = $("listen");
  const copyBtn = $("copy");
  const clearBtn = $("clear");
  const swapBtn = $("swap");
  const historyBtn = $("historyBtn");
  const darkModeBtn = $("darkMode");
  const aiBtn = $("aiBtn");
  const aiResult = $("aiResult");
  const historyList = $("historyList");

  let mediaRecorder = null;
  let audioChunks = [];
  let isRecording = false;
  let currentAudio = null;

  function showMessage(message, isError = false) {
    // Prefer a dedicated status element if your HTML has one.
    let status = $("status") || $("message");
    if (!status) {
      status = document.createElement("p");
      status.id = "status";
      status.setAttribute("role", "status");
      (resultBox?.parentElement || document.body).appendChild(status);
    }
    status.textContent = message;
    status.style.color = isError ? "#c62828" : "";
  }

  async function requestJson(url, options = {}) {
    let response;
    try {
      response = await fetch(url, options);
    } catch (error) {
      throw new Error("Server/network connection failed. Flask server run avutundo check cheyyandi.");
    }
    const contentType = response.headers.get("content-type") || "";
    const data = contentType.includes("application/json")
      ? await response.json()
      : { error: await response.text() };
    if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
    return data;
  }

  function postJson(url, body) {
    return requestJson(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
  }

  function selectedLanguage(select, fallback) {
    return select?.value || fallback;
  }

  function getSourceText() {
    return (speechInput?.value || "").trim();
  }

  function getResultText() {
    return (resultBox?.value ?? resultBox?.textContent ?? "").trim();
  }

  function setResultText(text) {
    if (!resultBox) return;
    if ("value" in resultBox) resultBox.value = text;
    else resultBox.textContent = text;
  }

  // Translation now uses the Groq API in app.py rather than GoogleTranslator,
  // which avoids the repeated Google Translate TooManyRequests error.
  translateBtn?.addEventListener("click", async () => {
    const text = getSourceText();
    if (!text) {
      showMessage("Munduga text type cheyyandi leda microphone use cheyyandi.", true);
      speechInput?.focus();
      return;
    }
    translateBtn.disabled = true;
    showMessage("Translating...");
    try {
      const data = await postJson("/translate", {
        text,
        from_lang: selectedLanguage(fromLang, "auto"),
        to_lang: selectedLanguage(toLang, "en")
      });
      setResultText(data.translated || "");
      showMessage("Translation complete.");
      loadHistory();
    } catch (error) {
      showMessage(error.message, true);
    } finally {
      translateBtn.disabled = false;
    }
  });

  // Use MediaRecorder + server-side Groq Whisper instead of browser
  // SpeechRecognition, which commonly fails with "network" errors.
  recordBtn?.addEventListener("click", async () => {
    if (isRecording && mediaRecorder) {
      mediaRecorder.stop();
      recordBtn.textContent = "Microphone";
      isRecording = false;
      return;
    }

    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      showMessage("Ee browser lo audio recording support ledu. Updated Chrome/Edge use cheyyandi.", true);
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunks = [];
      let mimeType = "";
      if (MediaRecorder.isTypeSupported("audio/webm;codecs=opus")) {
        mimeType = "audio/webm;codecs=opus";
      } else if (MediaRecorder.isTypeSupported("audio/webm")) {
        mimeType = "audio/webm";
      }
      mediaRecorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);

      mediaRecorder.addEventListener("dataavailable", (event) => {
        if (event.data && event.data.size > 0) audioChunks.push(event.data);
      });

      mediaRecorder.addEventListener("error", () => {
        showMessage("Audio recording lo error vachindi. Microphone permission check cheyyandi.", true);
      });

      mediaRecorder.addEventListener("stop", async () => {
        stream.getTracks().forEach((track) => track.stop());
        recordBtn.textContent = "Microphone";
        const blob = new Blob(audioChunks, { type: mediaRecorder?.mimeType || "audio/webm" });
        if (!blob.size) {
          showMessage("Audio record avvaledu. Malli try cheyyandi.", true);
          return;
        }
        showMessage("Audio ni text ga convert chestunnam...");
        const formData = new FormData();
        const ext = (blob.type.includes("mp4") || blob.type.includes("m4a")) ? "m4a" : "webm";
        formData.append("audio", blob, `recording.${ext}`);
        try {
          const data = await requestJson("/transcribe", { method: "POST", body: formData });
          if (speechInput) {
            speechInput.value = [speechInput.value.trim(), data.text].filter(Boolean).join(" ").trim();
          }
          showMessage("Microphone text ready. Ippudu Translate click cheyyandi.");
        } catch (error) {
          showMessage(error.message, true);
        }
      });

      mediaRecorder.start();
      isRecording = true;
      recordBtn.textContent = "Stop Recording";
      showMessage("Matladandi. Aipoyaka Stop Recording click cheyyandi.");
    } catch (error) {
      if (error.name === "NotAllowedError" || error.name === "PermissionDeniedError") {
        showMessage("Microphone permission Block ayindi. Browser site settings lo Microphone → Allow cheyyandi.", true);
      } else {
        showMessage(`Microphone start avvaledu: ${error.message || error.name}`, true);
      }
    }
  });

  listenBtn?.addEventListener("click", async () => {
    const text = getResultText() || getSourceText();
    if (!text) {
      showMessage("Listen cheyyadaniki text ledu.", true);
      return;
    }
    listenBtn.disabled = true;
    try {
      const data = await postJson("/speak", {
        text,
        language: selectedLanguage(toLang, "en")
      });
      if (currentAudio) {
        currentAudio.pause();
        currentAudio = null;
      }
      currentAudio = new Audio(data.audio);
      currentAudio.play().catch(() => showMessage("Audio play avvaledu. Browser lo sound/permission check cheyyandi.", true));
    } catch (error) {
      showMessage(error.message, true);
    } finally {
      listenBtn.disabled = false;
    }
  });

  copyBtn?.addEventListener("click", async () => {
    const text = getResultText();
    if (!text) return showMessage("Copy cheyyadaniki translated text ledu.", true);
    try {
      await navigator.clipboard.writeText(text);
      showMessage("Translated text copied.");
    } catch {
      showMessage("Copy fail ayindi. Result text select chesi Ctrl+C press cheyyandi.", true);
    }
  });

  clearBtn?.addEventListener("click", async () => {
    if (speechInput) speechInput.value = "";
    setResultText("");
    if (aiResult) aiResult.textContent = "";
    showMessage("Text cleared.");
  });

  swapBtn?.addEventListener("click", () => {
    if (!fromLang || !toLang) return;
    if (fromLang.value === "auto") {
      showMessage("Source language Auto-detect lo undi. Munduga source language select cheyyandi.", true);
      return;
    }
    const oldSource = fromLang.value;
    fromLang.value = toLang.value;
    toLang.value = oldSource;
  });

  historyBtn?.addEventListener("click", loadHistory);

  async function loadHistory() {
    if (!historyList) return;
    try {
      const rows = await requestJson("/history");
      historyList.replaceChildren();
      if (!Array.isArray(rows) || rows.length === 0) {
        historyList.textContent = "History empty.";
        return;
      }
      rows.forEach((row) => {
        const item = document.createElement("div");
        item.className = "history-item";
        const original = document.createElement("p");
        original.textContent = `Original: ${row[1] ?? ""}`;
        const translated = document.createElement("p");
        translated.textContent = `Translated: ${row[2] ?? ""}`;
        const details = document.createElement("small");
        details.textContent = `${row[3] ?? ""} → ${row[4] ?? ""} | ${row[5] ?? ""}`;
        item.append(original, translated, details);
        historyList.appendChild(item);
      });
    } catch (error) {
      showMessage(error.message, true);
    }
  }

  aiBtn?.addEventListener("click", async () => {
    const text = getSourceText() || getResultText();
    if (!text) {
      showMessage("AI explanation kosam text enter cheyyandi.", true);
      return;
    }
    aiBtn.disabled = true;
    if (aiResult) aiResult.textContent = "AI explanation loading...";
    try {
      const data = await postJson("/ai", { text });
      if (aiResult) aiResult.textContent = data.response || "";
      showMessage("AI explanation ready.");
    } catch (error) {
      if (aiResult) aiResult.textContent = error.message;
      showMessage(error.message, true);
    } finally {
      aiBtn.disabled = false;
    }
  });

  darkModeBtn?.addEventListener("click", () => {
    document.body.classList.toggle("dark-mode");
  });
});

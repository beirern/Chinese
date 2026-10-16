/* Optional, unscheduled practice. Only the selected voice/speed live in this page. */
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const scope = $("practice-scope");
  function updateFilters() {
    $("practice-source-choice").hidden = scope.value !== "source";
    $("practice-lesson-choices").hidden = scope.value !== "lessons";
  }
  scope.addEventListener("change", updateFilters);
  updateFilters();
  const words = JSON.parse($("practice-words").textContent);
  if (!words.length) { $("practice-selection").open = true; return; }
  const session = $("practice-session");
  session.hidden = false;
  let mode = document.querySelector(".practice-page").dataset.mode;
  let queue = [], current, revealed = false, speechToken = 0, speechTimer;
  let writer, guideToken = 0, activeCharacter = "", activeData = null, guideButton = null;
  let currentStroke = -1, isPlaying = false;
  const dataCache = new Map();
  const forms = () => [...new Set(current.traditional.split("/").map((s) => s.trim()).filter(Boolean))];

  function shuffled(items) {
    const result = [...items];
    for (let i = result.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [result[i], result[j]] = [result[j], result[i]];
    }
    // Avoid an immediate repeat between rounds.
    if (result.length > 1 && result[result.length - 1].id === current?.id) {
      [result[0], result[result.length - 1]] = [result[result.length - 1], result[0]];
    }
    return result;
  }

  const synth = window.speechSynthesis;
  let voices = [];
  function stopSpeech() {
    speechToken++;
    clearTimeout(speechTimer);
    if (synth) synth.cancel();
    $("speech-status").textContent = "";
  }
  function updateVoices() {
    const previous = $("practice-voice").value;
    voices = synth ? synth.getVoices().filter((voice) =>
      /^(zh|cmn)(-|_|$)/i.test(voice.lang) && !/[-_](HK|MO)\b/i.test(voice.lang)
    ) : [];
    const taiwan = (voice) => /^zh[-_]TW$/i.test(voice.lang) || /^cmn[-_]TW$/i.test(voice.lang);
    voices.sort((a, b) => Number(taiwan(b)) - Number(taiwan(a)) || a.name.localeCompare(b.name));
    $("practice-voice").replaceChildren();
    voices.forEach((voice) => $("practice-voice").add(new Option(`${voice.name} (${voice.lang})`, voice.voiceURI)));
    if (voices.some((voice) => voice.voiceURI === previous)) $("practice-voice").value = previous;
    if (!voices.length) $("practice-voice").add(new Option("No Mandarin voice available", ""));
    $("practice-voice").disabled = !voices.length;
    $("practice-play").disabled = !voices.length;
    $("pronunciation-hint").disabled = !voices.length;
    updateVoiceStatus();
  }
  function updateVoiceStatus() {
    const voice = voices.find((v) => v.voiceURI === $("practice-voice").value);
    $("voice-status").textContent = !synth
      ? "Speech is not supported in this browser. You can still practise on paper."
      : !voice ? "No Mandarin voice is available yet. Enable a Chinese speech voice on your device, then reload. Paper practice still works."
      : /[-_]TW$/i.test(voice.lang) ? "Using a Taiwan Mandarin voice."
      : "A Taiwan Mandarin voice is not selected. This voice may use a different pronunciation.";
  }
  function speak() {
    stopSpeech();
    const voice = voices.find((v) => v.voiceURI === $("practice-voice").value);
    if (!voice) return;
    const token = speechToken;
    const utterance = new SpeechSynthesisUtterance(forms()[0]);
    utterance.voice = voice;
    utterance.lang = voice.lang;
    utterance.rate = Number($("practice-speed").value);
    utterance.onstart = () => {
      if (token !== speechToken) return;
      clearTimeout(speechTimer);
      $("speech-status").textContent = "Playing…";
    };
    utterance.onend = () => {
      if (token === speechToken) {
        clearTimeout(speechTimer);
        $("speech-status").textContent = "";
      }
    };
    utterance.onerror = () => {
      if (token !== speechToken) return;
      clearTimeout(speechTimer);
      $("speech-status").textContent = "Could not play this voice. Choose another voice and try again.";
    };
    // Keep the utterance alive while the device speaks.
    session.utterance = utterance;
    $("speech-status").textContent = "Preparing audio…";
    speechTimer = setTimeout(() => {
      if (token === speechToken) {
        stopSpeech();
        $("speech-status").textContent = "Audio did not start. Try another voice or replay.";
      }
    }, 10000);
    synth.speak(utterance);
  }
  if (synth) synth.addEventListener("voiceschanged", updateVoices);
  $("practice-voice").addEventListener("change", () => { stopSpeech(); updateVoiceStatus(); });
  $("practice-speed").addEventListener("change", stopSpeech);
  $("practice-play").addEventListener("click", speak);
  $("pronunciation-hint").addEventListener("click", speak);
  $("pinyin-hint").addEventListener("click", () => {
    $("practice-hint").textContent = current.pinyin;
    $("practice-hint").hidden = false;
  });
  window.addEventListener("pagehide", stopSpeech);
  updateVoices();

  function resetGuide() {
    guideToken++;
    if (writer) writer.pauseAnimation();
    writer = null;
    activeCharacter = "";
    activeData = null;
    guideButton = null;
    currentStroke = -1;
    isPlaying = false;
    $("guide-target").replaceChildren();
    $("guide-play").disabled = true;
    $("guide-play").textContent = "Play strokes";
    $("guide-previous").disabled = true;
    $("guide-next").disabled = true;
    $("guide-speed").disabled = true;
    $("guide-step").textContent = "";
    $("guide-status").textContent = "";
  }
  async function characterData(character) {
    if (dataCache.has(character)) return dataCache.get(character);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch(`https://cdn.jsdelivr.net/npm/hanzi-writer-data@2.0.1/${encodeURIComponent(character)}.json`, { signal: controller.signal });
      if (!response.ok) throw new Error("Missing character");
      const data = await response.json();
      if (!data.strokes?.length || data.strokes.length !== data.medians?.length) throw new Error("Invalid character data");
      dataCache.set(character, data);
      return data;
    } finally { clearTimeout(timeout); }
  }
  async function showCharacter(character, button) {
    resetGuide();
    const token = guideToken;
    $("guide-characters").querySelectorAll("button").forEach((item) => item.setAttribute("aria-pressed", String(item === button)));
    $("guide-status").textContent = "Loading stroke guide…";
    try {
      if (!window.HanziWriter) throw new Error("Library unavailable");
      const data = await characterData(character);
      if (token !== guideToken) return;
      activeCharacter = character;
      activeData = data;
      guideButton = button;
      const size = Math.min(260, $("guide-target").getBoundingClientRect().width);
      const faster = $("guide-speed").value === "fast";
      writer = HanziWriter.create("guide-target", character, {
        width: size, height: size, padding: 18,
        strokeColor: "#20252b", outlineColor: "#deded8", drawingColor: "#175b72",
        highlightColor: "#175b72", showCharacter: true, showOutline: true,
        strokeAnimationSpeed: faster ? 2.5 : 1,
        delayBetweenStrokes: faster ? 80 : 500,
        charDataLoader: () => data,
      });
      $("guide-play").disabled = false;
      $("guide-previous").disabled = true;
      $("guide-next").disabled = false;
      $("guide-speed").disabled = false;
      $("guide-step").textContent = `${data.strokes.length} strokes`;
      $("guide-status").textContent = "Write on paper and use the controls to review stroke order.";
    } catch {
      if (token === guideToken) $("guide-status").textContent = "Stroke playback is unavailable for this character. Try selecting it again when online.";
    }
  }
  function selectForm() {
    resetGuide();
    $("guide-characters").replaceChildren();
    const characters = [...$("guide-form").value].filter((c) => /\p{Script=Han}/u.test(c));
    characters.forEach((character, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = character;
      button.lang = "zh-Hant";
      button.setAttribute("aria-label", `Character ${index + 1}: ${character}`);
      button.addEventListener("click", () => showCharacter(character, button));
      $("guide-characters").append(button);
    });
    const first = $("guide-characters").querySelector("button");
    if (first) first.click();
    else $("guide-status").textContent = "No character stroke guide is available for this expression.";
  }
  $("guide-form").addEventListener("change", selectForm);
  $("stroke-guide").addEventListener("toggle", () => {
    if ($("stroke-guide").open && revealed) selectForm();
    else resetGuide();
  });
  $("guide-play").addEventListener("click", () => {
    if (!writer) return;
    if (isPlaying) {
      writer.pauseAnimation();
      isPlaying = false;
      $("guide-play").textContent = "Resume strokes";
      $("guide-status").textContent = "Playback paused.";
      return;
    }
    if ($("guide-play").textContent === "Resume strokes") {
      writer.resumeAnimation();
      isPlaying = true;
      $("guide-play").textContent = "Pause";
      $("guide-status").textContent = "Playing stroke order…";
      return;
    }
    isPlaying = true;
    $("guide-play").textContent = "Pause";
    $("guide-status").textContent = "Playing stroke order…";
    const token = guideToken;
    writer.animateCharacter({ onComplete: () => {
      if (token !== guideToken || !activeData) return;
      isPlaying = false;
      currentStroke = activeData.strokes.length - 1;
      updateStrokeControls();
      $("guide-play").textContent = "Play again";
      $("guide-status").textContent = "Stroke sequence complete.";
    } });
  });
  function updateStrokeControls() {
    if (!activeData) return;
    $("guide-previous").disabled = currentStroke <= 0;
    $("guide-next").disabled = currentStroke >= activeData.strokes.length - 1;
    $("guide-step").textContent = currentStroke < 0
      ? `${activeData.strokes.length} strokes · ready`
      : `Stroke ${currentStroke + 1} of ${activeData.strokes.length}`;
  }
  function playSingleStroke(index) {
    if (!writer || !activeData || index < 0 || index >= activeData.strokes.length) return;
    if (isPlaying) writer.pauseAnimation();
    isPlaying = false;
    $("guide-play").textContent = "Play strokes";
    currentStroke = index;
    updateStrokeControls();
    $("guide-status").textContent = `Showing stroke ${index + 1}.`;
    writer.animateStroke(index);
  }
  $("guide-previous").addEventListener("click", () => playSingleStroke(currentStroke <= 0 ? 0 : currentStroke - 1));
  $("guide-next").addEventListener("click", () => playSingleStroke(currentStroke + 1));
  $("guide-speed").addEventListener("change", () => {
    if (activeCharacter && guideButton) showCharacter(activeCharacter, guideButton);
  });

  function hideAnswer() {
    revealed = false;
    $("practice-answer").hidden = true;
    $("stroke-guide").open = true;
    resetGuide();
    $("practice-hint").hidden = true;
    $("practice-hint").textContent = "";
    $("practice-reveal").hidden = false;
    $("practice-next").textContent = "Skip word";
  }
  function nextWord() {
    stopSpeech();
    if (!queue.length) queue = shuffled(words);
    current = queue.pop();
    $("writing-meaning").textContent = current.english;
    hideAnswer();
  }
  function setMode(value) {
    mode = value;
    stopSpeech();
    $("filter-mode").value = mode;
    $("listening-prompt").hidden = mode !== "listening";
    $("writing-prompt").hidden = mode !== "writing";
    document.querySelectorAll(".practice-modes button").forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.mode === mode)));
    hideAnswer();
  }
  document.querySelectorAll(".practice-modes button").forEach((button) => button.addEventListener("click", () => setMode(button.dataset.mode)));
  $("practice-next").addEventListener("click", nextWord);
  $("practice-reveal").addEventListener("click", () => {
    revealed = true;
    $("answer-chinese").textContent = current.traditional;
    $("answer-pinyin").textContent = current.pinyin;
    $("answer-english").textContent = current.english;
    $("answer-lessons").replaceChildren();
    current.lessons.forEach((lesson) => {
      const li = document.createElement("li");
      li.textContent = lesson;
      $("answer-lessons").append(li);
    });
    $("guide-form").replaceChildren();
    forms().forEach((form) => $("guide-form").add(new Option(form, form)));
    $("practice-answer").hidden = false;
    $("practice-reveal").hidden = true;
    $("practice-next").textContent = "Next word";
    if ($("stroke-guide").open) selectForm();
  });
  nextWord();
  setMode(mode);
})();

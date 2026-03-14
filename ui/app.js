const previews = {
  morning: {
    meta: "朝 / 170-280文字",
    text: "『悪くないけど何か足りない』と感じる瞬間は、見る目が先に育っているサインです。今後3〜6ヶ月は、見た目の派手さより設計意図を説明できるアウトプットがより評価される流れが強まりそう。まずは直近の制作物を1つだけ見返し、惜しい点を3行で言語化してみてください。",
  },
  noon: {
    meta: "昼 / 90-180文字",
    text: "今日のAIトピックは、実装速度より運用設計の差が出る流れ。\n\nまずは1工程だけ自動化して、レビュー時間がどれだけ減るかを見たいです。\n\n#AI活用 #デザイン #業務改善",
  },
  evening: {
    meta: "夕方 / 110-220文字",
    text: "今日は進みが遅くてもOK。AI時代は、速さより続けられる改善の積み上げが効きます。今夜は『うまくいった判断』を1行だけ残して終わりで十分です。",
  },
};

let selectedSlot = "morning";
const ENV_KEYS = [
  "OPENAI_API_KEY",
  "X_BEARER_TOKEN",
  "X_API_KEY",
  "X_API_SECRET",
  "X_ACCESS_TOKEN",
  "X_ACCESS_SECRET",
  "GOOGLE_API_KEY",
  "NANOBANANA_CMD_TEMPLATE",
  "FREEPIK_API_KEY",
];

const cards = document.querySelectorAll(".slot-card");
const topPageButtons = document.querySelectorAll(".menu .pill[data-page]");
const railPageButtons = document.querySelectorAll(".rail-btn[data-page]");
const pageCards = document.querySelectorAll(".main-grid > article[data-page]");
const previewMeta = document.getElementById("previewMeta");
const previewEditor = document.getElementById("previewEditor");
const previewCount = document.getElementById("previewCount");
const xPreviewText = document.getElementById("xPreviewText");
const xPreviewHandle = document.getElementById("xPreviewHandle");
const xPreviewName = document.getElementById("xPreviewName");
const xPreviewAvatar = document.getElementById("xPreviewAvatar");
const runOutput = document.getElementById("runOutput");
const accountChip = document.getElementById("accountChip");
const accountName = document.getElementById("accountName");
const followers = document.getElementById("followers");
const tweetCount = document.getElementById("tweetCount");
const accountMessage = document.getElementById("accountMessage");
const targetAccountInput = document.getElementById("targetAccountInput");
const targetAccountMessage = document.getElementById("targetAccountMessage");
const envMessage = document.getElementById("envMessage");
const mediaMessage = document.getElementById("mediaMessage");
const pdfMessage = document.getElementById("pdfMessage");
const pdfUploadInput = document.getElementById("pdfUploadInput");
const pdfListBody = document.getElementById("pdfListBody");
const draftLabMessage = document.getElementById("draftLabMessage");
const draftProgressWrap = document.getElementById("draftProgressWrap");
const draftProgressBar = document.getElementById("draftProgressBar");
const draftProgressText = document.getElementById("draftProgressText");
const generatedMediaMessage = document.getElementById("generatedMediaMessage");
const generatedMediaPreview = document.getElementById("generatedMediaPreview");
const imageProgressWrap = document.getElementById("imageProgressWrap");
const imageProgressBar = document.getElementById("imageProgressBar");
const imageProgressText = document.getElementById("imageProgressText");
const planStartDate = document.getElementById("planStartDate");
const planUnit = document.getElementById("planUnit");
const planCount = document.getElementById("planCount");
const planEveryDay = document.getElementById("planEveryDay");
const planMessage = document.getElementById("planMessage");
const planProgressWrap = document.getElementById("planProgressWrap");
const planProgressBar = document.getElementById("planProgressBar");
const planProgressText = document.getElementById("planProgressText");
const planTbody = document.getElementById("planTbody");
const queueTbody = document.getElementById("queueTbody");
const queueMessage = document.getElementById("queueMessage");
const railHint = document.getElementById("railHint");
const generateImageBtn = document.getElementById("generateImageBtn");
const deleteSelectedQueueBtn = document.getElementById("deleteSelectedQueueBtn");
const clearQueueBtn = document.getElementById("clearQueueBtn");
const imageModal = document.getElementById("imageModal");
const imageModalPreview = document.getElementById("imageModalPreview");
const imageModalCloseBtn = document.getElementById("imageModalCloseBtn");

let currentPlan = [];
let currentQueue = [];
let generatedMediaPath = "";
let currentPage = "dashboard";
let imageCooldownTimer = null;
let planGenerationNonce = 0;
const PLAN_VISUAL_MODE_OPTIONS = [
  ["auto", "自動ローテーション"],
  ["design_case", "デザイン事例"],
  ["diagram", "図解/概念図"],
  ["editorial", "エディトリアル"],
  ["photo", "写真ベース"],
];

function showButtonSuccess(button, text = "Success!") {
  if (!(button instanceof HTMLElement)) return;
  const rect = button.getBoundingClientRect();
  const bubble = document.createElement("div");
  bubble.className = "action-bubble";
  bubble.textContent = text;
  bubble.style.left = `${rect.left + rect.width / 2}px`;
  bubble.style.top = `${Math.max(12, rect.top - 10)}px`;
  document.body.appendChild(bubble);
  requestAnimationFrame(() => bubble.classList.add("show"));
  window.setTimeout(() => {
    bubble.classList.remove("show");
    window.setTimeout(() => bubble.remove(), 260);
  }, 1150);
}

function slotLabel(slot) {
  if (slot === "morning") return "朝";
  if (slot === "noon") return "昼";
  if (slot === "evening") return "夕方";
  return slot || "-";
}

function getExpectedMs(task, fallbackMs) {
  const raw = Number(localStorage.getItem(`op_avg_ms_${task}`) || 0);
  return raw > 0 ? raw : fallbackMs;
}

function saveObservedMs(task, elapsedMs) {
  const key = `op_avg_ms_${task}`;
  const prev = Number(localStorage.getItem(key) || 0);
  const next = prev > 0 ? Math.round(prev * 0.7 + elapsedMs * 0.3) : elapsedMs;
  localStorage.setItem(key, String(next));
}

function formatRemain(ms) {
  const sec = Math.max(0, Math.ceil(ms / 1000));
  return `${sec}秒`;
}

function startProgress(task, wrapEl, barEl, textEl, fallbackMs) {
  const expectedMs = getExpectedMs(task, fallbackMs);
  wrapEl.classList.add("show");
  const startedAt = Date.now();
  barEl.style.width = "2%";
  textEl.textContent = `進行中 0%（残り約${formatRemain(expectedMs)}）`;

  const timer = setInterval(() => {
    const elapsed = Date.now() - startedAt;
    const ratio = Math.min(0.92, elapsed / expectedMs);
    const pct = Math.max(1, Math.min(92, Math.round(ratio * 100)));
    barEl.style.width = `${pct}%`;
    const remainMs = Math.max(0, expectedMs - elapsed);
    textEl.textContent = `進行中 ${pct}%（残り約${formatRemain(remainMs)}）`;
  }, 180);

  return {
    done(ok = true) {
      clearInterval(timer);
      const elapsed = Date.now() - startedAt;
      saveObservedMs(task, elapsed);
      barEl.style.width = "100%";
      textEl.textContent = ok
        ? `完了 100%（${Math.ceil(elapsed / 1000)}秒）`
        : `失敗 ${Math.min(99, Math.round((elapsed / expectedMs) * 100))}%（${Math.ceil(elapsed / 1000)}秒）`;
    },
  };
}

function startInlineProgress(task, wrapEl, barEl, textEl, fallbackMs) {
  const expectedMs = getExpectedMs(task, fallbackMs);
  wrapEl.classList.add("show");
  const startedAt = Date.now();
  barEl.style.width = "2%";
  textEl.textContent = `生成中 0%（残り約${formatRemain(expectedMs)}）`;

  const timer = setInterval(() => {
    const elapsed = Date.now() - startedAt;
    const ratio = Math.min(0.94, elapsed / expectedMs);
    const pct = Math.max(1, Math.min(94, Math.round(ratio * 100)));
    barEl.style.width = `${pct}%`;
    textEl.textContent = `生成中 ${pct}%（残り約${formatRemain(Math.max(0, expectedMs - elapsed))})`;
  }, 180);

  return {
    done(ok = true) {
      clearInterval(timer);
      const elapsed = Date.now() - startedAt;
      saveObservedMs(task, elapsed);
      barEl.style.width = "100%";
      textEl.textContent = ok ? `生成完了 100%（${Math.ceil(elapsed / 1000)}秒）` : `生成失敗`;
    },
  };
}

function buildCountOptions(max, selected = 1) {
  const options = Array.from({ length: max }, (_, i) => i + 1)
    .map((n) => `<option value="${n}" ${n === selected ? "selected" : ""}>${n}</option>`)
    .join("");
  planCount.innerHTML = options;
}

function updateCountSelector() {
  const unit = planUnit.value;
  const current = Number(planCount.value || 1);
  const max = unit === "days" ? 31 : 12;
  const selected = Math.min(Math.max(current, 1), max);
  buildCountOptions(max, selected);
}

async function fetchJson(url, options = {}) {
  const res = await fetch(url, options);
  const raw = await res.text();
  let data = null;
  try {
    data = raw ? JSON.parse(raw) : {};
  } catch (_e) {
    const body = raw.slice(0, 220).replace(/\n/g, " ");
    throw new Error(`サーバーがJSON以外を返しました (${res.status}): ${body}`);
  }
  if (!res.ok || (data && data.ok === false)) {
    const msg = (data && (data.message || data.error)) || `APIエラー (${res.status})`;
    const err = new Error(msg);
    err.status = res.status;
    err.payload = data || {};
    throw err;
  }
  return data;
}

async function fetchFormJson(url, formData) {
  const res = await fetch(url, { method: "POST", body: formData });
  const raw = await res.text();
  let data = null;
  try {
    data = raw ? JSON.parse(raw) : {};
  } catch (_e) {
    const body = raw.slice(0, 220).replace(/\n/g, " ");
    throw new Error(`サーバーがJSON以外を返しました (${res.status}): ${body}`);
  }
  if (!res.ok || (data && data.ok === false)) {
    const msg = (data && (data.message || data.error)) || `APIエラー (${res.status})`;
    throw new Error(msg);
  }
  return data;
}

function setPreview(slot) {
  selectedSlot = slot;
  previewMeta.textContent = previews[slot].meta;
  previewEditor.value = previews[slot].text;
  updateXPreview(previewEditor.value);
}

function toDateTimeLocal(dateText, timeText) {
  return `${dateText}T${timeText}`;
}

function fromDateTimeLocal(value) {
  const [d, t = "09:00"] = value.split("T");
  return { date: d, time: t.slice(0, 5) };
}

function updateXPreview(text) {
  const value = (text || "").trim();
  xPreviewText.textContent = value || "ここに投稿プレビューが表示されます。";
  previewCount.textContent = `${value.length}文字`;
}

function setXIdentity(handle, name = "") {
  const cleanHandle = (handle || "@your_account").startsWith("@") ? handle : `@${handle}`;
  xPreviewHandle.textContent = cleanHandle;
  xPreviewName.textContent = name || "Uzu";
  const initial = (cleanHandle.replace("@", "").charAt(0) || "U").toUpperCase();
  xPreviewAvatar.textContent = initial;
}

function esc(v) {
  return String(v ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function canPlanGenerateImage(slot) {
  return slot === "morning" || slot === "evening";
}

function getDefaultVisualMode() {
  return (document.getElementById("visualModeSelect")?.value || "auto").trim() || "auto";
}

function buildVisualModeOptions(selected) {
  return PLAN_VISUAL_MODE_OPTIONS.map(
    ([value, label]) => `<option value="${esc(value)}"${value === selected ? " selected" : ""}>${esc(label)}</option>`,
  ).join("");
}

function normalizePlanItem(item) {
  return {
    ...item,
    media_path: item.media_path || "",
    media_url: item.media_url || "",
    media_name: item.media_name || "",
    media_visual_mode: item.media_visual_mode || getDefaultVisualMode(),
    media_approved: !!item.media_approved,
    media_generating: !!item.media_generating,
  };
}

function planMediaStatusLabel(row) {
  if (!canPlanGenerateImage(row.slot)) return "対象外";
  if (row.media_generating) return "生成中";
  if (row.media_approved && row.media_path) return "添付予定";
  if (row.media_path) return "生成済み";
  return "未生成";
}

function getModalImageSrc(img) {
  if (!(img instanceof HTMLImageElement)) return "";
  return img.currentSrc || img.getAttribute("src") || "";
}

function openImageInWindow(src) {
  if (!src) return;
  const nextWindow = window.open("", "_blank", "noopener,noreferrer");
  if (!nextWindow) {
    window.open(src, "_blank", "noopener,noreferrer");
    return;
  }
  const safeSrc = JSON.stringify(src);
  nextWindow.document.write(`<!doctype html>
<html lang="ja">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>画像プレビュー</title>
    <style>
      :root { color-scheme: light; }
      body {
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        background: #101010;
        font-family: "Hiragino Sans", "Yu Gothic", sans-serif;
      }
      img {
        max-width: 96vw;
        max-height: 94vh;
        object-fit: contain;
        border-radius: 18px;
        box-shadow: 0 24px 60px rgba(0, 0, 0, 0.4);
        background: #202020;
      }
    </style>
  </head>
  <body>
    <img src=${safeSrc} alt="preview" />
  </body>
</html>`);
  nextWindow.document.close();
}

function setAccountStatusConnected({ username, name, followers: f, tweet_count: t }) {
  accountChip.textContent = "連動済み";
  accountName.textContent = username ? `@${username}` : "-";
  followers.textContent = Number.isFinite(Number(f)) ? String(f) : "-";
  tweetCount.textContent = Number.isFinite(Number(t)) ? String(t) : "-";
  accountMessage.textContent = name
    ? `${name} と連動できています。`
    : "Xアカウント連動を確認しました。";
}

async function checkAccount() {
  accountChip.textContent = "確認中...";
  accountMessage.textContent = "X APIへ接続中...";
  try {
    const data = await fetchJson("/api/account");
    setAccountStatusConnected(data);
    showButtonSuccess(document.getElementById("checkAccountBtn"));
  } catch (e) {
    accountChip.textContent = "エラー";
    accountMessage.textContent = `X連動エラー: ${e}`;
  }
}

async function runDry(slot) {
  const slotLabel = slot === "morning" ? "朝" : slot === "noon" ? "昼" : slot === "evening" ? "夕方" : slot;
  runOutput.textContent = `${slotLabel}枠のドライランを実行中...`;
  try {
    const data = await fetchJson("/api/run_dry", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slot }),
    });
    runOutput.textContent = data.output || data.message || "出力はありません。";
    const button =
      document.querySelector(`.slot-run[data-slot="${slot}"]`) ||
      (selectedSlot === slot ? document.getElementById("runSelectedBtn") : null);
    showButtonSuccess(button);
  } catch (e) {
    runOutput.textContent = `実行エラー: ${e}`;
  }
}

async function testPost() {
  const text = (previewEditor.value || "").trim();
  if (!text) {
    runOutput.textContent = "試験投稿する本文がありません。";
    return;
  }
  if (!confirm("この内容をXへ試験投稿します。続行しますか？")) {
    return;
  }
  runOutput.textContent = "試験投稿中...";
  try {
    const fileInput = document.getElementById("testMediaFile");
    const sourceUrl = (document.getElementById("testSourceUrl")?.value || "").trim();
    const attachSourceReply = !!document.getElementById("testAttachSourceReply")?.checked;
    const useGeneratedMedia = !!document.getElementById("useGeneratedMediaForTest")?.checked;
    const hasFile = !!(fileInput && fileInput.files && fileInput.files[0]);
    const mediaPath = useGeneratedMedia ? generatedMediaPath : "";
    let data = null;
    if (hasFile) {
      const form = new FormData();
      form.append("text", text);
      form.append("media", fileInput.files[0]);
      if (sourceUrl) form.append("source_url", sourceUrl);
      if (attachSourceReply) form.append("attach_source_reply", "true");
      if (mediaPath) form.append("media_path", mediaPath);
      data = await fetchFormJson("/api/test_post", form);
    } else {
      data = await fetchJson("/api/test_post", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text,
          source_url: sourceUrl,
          attach_source_reply: attachSourceReply,
          media_path: mediaPath,
        }),
      });
    }
    runOutput.textContent = `${data.message}\n投稿ID: ${data.tweet_id}\n${data.tweet_url || ""}`;
    if (fileInput) fileInput.value = "";
    showButtonSuccess(document.getElementById("testPostBtn"));
  } catch (e) {
    runOutput.textContent = `試験投稿エラー: ${e}`;
  }
}

async function generateDraft() {
  const topic = (document.getElementById("draftTopicInput")?.value || "").trim();
  if (!topic) {
    draftLabMessage.textContent = "テーマ/キーワードを入力してください。";
    return;
  }
  draftLabMessage.textContent = "投稿文を生成中...";
  const p = startProgress("draft", draftProgressWrap, draftProgressBar, draftProgressText, 7000);
  try {
    const data = await fetchJson("/api/draft_lab_generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic, slot: selectedSlot }),
    });
    previewEditor.value = data.text || "";
    updateXPreview(previewEditor.value);
    const reason = (data.reason || "").trim();
    draftLabMessage.textContent = reason ? `生成OK: ${reason}` : "投稿文を生成しました。";
    p.done(true);
    showButtonSuccess(document.getElementById("generateDraftBtn"));
  } catch (e) {
    draftLabMessage.textContent = `生成エラー: ${e}`;
    p.done(false);
  }
}

function startImageCooldown(seconds) {
  const total = Math.max(1, Number(seconds || 0));
  if (!generateImageBtn) return;
  if (imageCooldownTimer) {
    clearInterval(imageCooldownTimer);
    imageCooldownTimer = null;
  }
  let remain = total;
  const baseLabel = "画像を生成";
  generateImageBtn.disabled = true;
  generateImageBtn.textContent = `${baseLabel} (${remain}秒)`;
  imageCooldownTimer = setInterval(() => {
    remain -= 1;
    if (remain <= 0) {
      clearInterval(imageCooldownTimer);
      imageCooldownTimer = null;
      generateImageBtn.disabled = false;
      generateImageBtn.textContent = baseLabel;
      return;
    }
    generateImageBtn.textContent = `${baseLabel} (${remain}秒)`;
  }, 1000);
}

async function generateImageFromDraft() {
  const text = (previewEditor.value || "").trim();
  const visualMode = (document.getElementById("visualModeSelect")?.value || "auto").trim() || "auto";
  if (!text) {
    generatedMediaMessage.textContent = "先に投稿文を作成してください。";
    return;
  }
  generatedMediaMessage.textContent = "画像生成中...";
  generatedMediaPreview.classList.remove("show");
  const p = startProgress("image", imageProgressWrap, imageProgressBar, imageProgressText, 14000);
  try {
    const data = await fetchJson("/api/generate_image", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, visual_mode: visualMode }),
    });
    generatedMediaPath = data.path || "";
    const url = data.url || "";
    const usedMode = data.visual_mode || visualMode;
    if (!url) throw new Error("画像URLを取得できませんでした。");
    generatedMediaPreview.src = `${url}?t=${Date.now()}`;
    generatedMediaPreview.classList.add("show");
    generatedMediaMessage.textContent = `画像を生成しました（モード: ${usedMode}）。必要なら試験投稿へ添付できます。`;
    p.done(true);
    showButtonSuccess(document.getElementById("generateImageBtn"));
  } catch (e) {
    generatedMediaPath = "";
    const retrySec = Number(e?.payload?.retry_after_sec || 0);
    if (retrySec > 0) {
      generatedMediaMessage.textContent = `画像生成エラー: ${e} / 再試行推奨まで ${retrySec}秒`;
      startImageCooldown(retrySec);
    } else {
      generatedMediaMessage.textContent = `画像生成エラー: ${e}`;
    }
    p.done(false);
  }
}

async function loadTargetAccount() {
  try {
    const data = await fetchJson("/api/target_account");
    targetAccountInput.value = data.account_handle || "";
    setXIdentity(data.account_handle || "@your_account");
  } catch (e) {
    targetAccountMessage.textContent = `連結先読み込みエラー: ${e}`;
  }
}

async function saveTargetAccount() {
  const account_handle = targetAccountInput.value.trim();
  if (!account_handle) {
    targetAccountMessage.textContent = "連結するXアカウントを入力してください。";
    return;
  }
  targetAccountMessage.textContent = "保存中...";
  try {
    const data = await fetchJson("/api/target_account", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ account_handle }),
    });
    targetAccountMessage.textContent = data.message || "保存しました。";
    targetAccountInput.value = data.account_handle;
    setXIdentity(data.account_handle);
    showButtonSuccess(document.getElementById("saveTargetBtn"));
  } catch (e) {
    targetAccountMessage.textContent = `保存エラー: ${e}`;
  }
}

async function verifyTargetAccount() {
  const account_handle = targetAccountInput.value.trim();
  if (!account_handle) {
    targetAccountMessage.textContent = "確認したいXアカウントを入力してください。";
    return;
  }
  targetAccountMessage.textContent = "X上で確認中...";
  try {
    const data = await fetchJson("/api/verify_target_account", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ account_handle }),
    });
    const verifiedText = data.verified ? " / 認証済み" : "";
    targetAccountMessage.textContent = `確認OK: @${data.username} (${data.name}) / followers ${data.followers}${verifiedText}`;
    // 運用対象アカウント確認時にも上部カードを更新する
    setAccountStatusConnected({
      username: data.username,
      name: data.name,
      followers: data.followers,
      tweet_count: data.tweet_count ?? "-",
    });
    setXIdentity(`@${data.username}`, data.name);
    showButtonSuccess(document.getElementById("verifyTargetBtn"));
  } catch (e) {
    targetAccountMessage.textContent = `確認エラー: ${e}`;
  }
}

async function loadEnvStatus() {
  try {
    const data = await fetchJson("/api/env");
    ENV_KEYS.forEach((key) => {
      const maskEl = document.getElementById(`mask_${key}`);
      const item = data.env[key];
      maskEl.textContent = item && item.is_set ? `保存済み: ${item.masked}` : "未設定";
    });
    envMessage.textContent = "現在の保存状態を読み込みました。";
  } catch (e) {
    envMessage.textContent = `環境変数読み込みエラー: ${e}`;
  }
}

async function saveEnv() {
  const env = {};
  let changed = 0;
  ENV_KEYS.forEach((key) => {
    const value = document.getElementById(key).value.trim();
    if (value) {
      env[key] = value;
      changed += 1;
    }
  });
  if (changed === 0) {
    envMessage.textContent = "入力されたキーがありません。更新したい項目だけ入力してください。";
    return;
  }
  envMessage.textContent = "保存中...";
  try {
    const data = await fetchJson("/api/env", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ env }),
    });
    envMessage.textContent = data.message || "保存しました。";
    ENV_KEYS.forEach((key) => {
      document.getElementById(key).value = "";
    });
    await loadEnvStatus();
    showButtonSuccess(document.getElementById("saveEnvBtn"));
  } catch (e) {
    envMessage.textContent = `保存エラー: ${e}`;
  }
}

async function loadMediaConfig() {
  try {
    const data = await fetchJson("/api/media_config");
    const media = data.media || {};
    document.getElementById("media_enabled").checked = !!media.enabled;
    document.getElementById("media_morning_generate_image").checked = !!media.morning_generate_image;
    document.getElementById("media_morning_image_provider").value = media.morning_image_provider || "nanobanana_pro";
    document.getElementById("media_morning_image_output_dir").value = media.morning_image_output_dir || "generated_media";
    document.getElementById("media_noon_reply_source_link").checked = !!media.noon_reply_source_link;
    mediaMessage.textContent = "メディア設定を読み込みました。";
  } catch (e) {
    mediaMessage.textContent = `メディア設定読み込みエラー: ${e}`;
  }
}

async function saveMediaConfig() {
  mediaMessage.textContent = "保存中...";
  const media = {
    enabled: !!document.getElementById("media_enabled").checked,
    morning_generate_image: !!document.getElementById("media_morning_generate_image").checked,
    morning_image_provider: document.getElementById("media_morning_image_provider").value,
    morning_image_output_dir: document.getElementById("media_morning_image_output_dir").value.trim() || "generated_media",
    noon_reply_source_link: !!document.getElementById("media_noon_reply_source_link").checked,
  };
  try {
    const data = await fetchJson("/api/media_config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ media }),
    });
    mediaMessage.textContent = data.message || "メディア設定を保存しました。";
    showButtonSuccess(document.getElementById("saveMediaBtn"));
  } catch (e) {
    mediaMessage.textContent = `メディア設定保存エラー: ${e}`;
  }
}

function renderPdfLibrary(docs) {
  if (!pdfListBody) return;
  if (!Array.isArray(docs) || docs.length === 0) {
    pdfListBody.innerHTML = "<tr><td colspan='7'>PDFはまだありません。</td></tr>";
    return;
  }
  const html = docs
    .map(
      (d) => `
      <tr data-pdf-id="${esc(d.id || "")}">
        <td>${esc(d.original_name || "-")}</td>
        <td>${esc(d.pages ?? "-")}</td>
        <td>${esc(d.char_count ?? "-")}</td>
        <td>
          <select class="pdf-priority">
            <option value="5" ${Number(d.priority || 3) === 5 ? "selected" : ""}>5</option>
            <option value="4" ${Number(d.priority || 3) === 4 ? "selected" : ""}>4</option>
            <option value="3" ${Number(d.priority || 3) === 3 ? "selected" : ""}>3</option>
            <option value="2" ${Number(d.priority || 3) === 2 ? "selected" : ""}>2</option>
            <option value="1" ${Number(d.priority || 3) === 1 ? "selected" : ""}>1</option>
          </select>
        </td>
        <td>
          <select class="pdf-scope">
            <option value="all" ${String(d.scope || "all") === "all" ? "selected" : ""}>全スロット</option>
            <option value="morning" ${String(d.scope || "all") === "morning" ? "selected" : ""}>朝だけ</option>
          </select>
        </td>
        <td>${esc(d.uploaded_at || "-")}</td>
        <td>
          <button class="ghost pdf-save-btn" data-pdf-id="${esc(d.id || "")}">設定保存</button>
          <button class="ghost pdf-delete-btn" data-pdf-id="${esc(d.id || "")}">削除</button>
        </td>
      </tr>
    `,
    )
    .join("");
  pdfListBody.innerHTML = html;
}

async function loadPdfLibrary() {
  if (!pdfMessage) return;
  pdfMessage.textContent = "PDF一覧を読み込み中...";
  try {
    const data = await fetchJson("/api/pdf_library");
    const docs = data.docs || [];
    renderPdfLibrary(docs);
    pdfMessage.textContent = `${docs.length}件のPDFをストック中です。`;
  } catch (e) {
    pdfMessage.textContent = `PDF一覧読み込みエラー: ${e}`;
  }
}

async function uploadPdf() {
  if (!pdfUploadInput || !pdfMessage) return;
  const file = pdfUploadInput.files && pdfUploadInput.files[0];
  if (!file) {
    pdfMessage.textContent = "アップロードするPDFを選択してください。";
    return;
  }
  pdfMessage.textContent = "PDFを取り込み中...";
  const form = new FormData();
  form.append("pdf", file);
  try {
    const data = await fetchFormJson("/api/pdf_library/upload", form);
    renderPdfLibrary(data.docs || []);
    pdfMessage.textContent = data.message || "PDFを追加しました。";
    pdfUploadInput.value = "";
    showButtonSuccess(document.getElementById("uploadPdfBtn"));
  } catch (e) {
    pdfMessage.textContent = `PDF追加エラー: ${e}`;
  }
}

async function deletePdf(docId) {
  if (!docId || !pdfMessage) return;
  if (!confirm("このPDFをストックから削除しますか？")) return;
  pdfMessage.textContent = "PDFを削除中...";
  try {
    const data = await fetchJson(`/api/pdf_library/${encodeURIComponent(docId)}`, { method: "DELETE" });
    renderPdfLibrary(data.docs || []);
    pdfMessage.textContent = data.message || "PDFを削除しました。";
    showButtonSuccess(document.activeElement);
  } catch (e) {
    pdfMessage.textContent = `PDF削除エラー: ${e}`;
  }
}

async function updatePdfSettings(docId, priority, scope) {
  if (!docId || !pdfMessage) return;
  pdfMessage.textContent = "PDF設定を保存中...";
  try {
    const data = await fetchJson("/api/pdf_library/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        doc_id: docId,
        priority: Number(priority || 3),
        scope: (scope || "all").trim(),
      }),
    });
    renderPdfLibrary(data.docs || []);
    pdfMessage.textContent = data.message || "PDF設定を更新しました。";
    showButtonSuccess(document.activeElement);
  } catch (e) {
    pdfMessage.textContent = `PDF設定更新エラー: ${e}`;
  }
}

function renderPlanRows(items) {
  if (!items.length) {
    planTbody.innerHTML = "<tr><td colspan='6'>投稿予定はありません。</td></tr>";
    return;
  }
  const html = items
    .map(
      (row, idx) => `
      <tr data-plan-idx="${idx}">
        <td>${row.date}</td>
        <td>${row.time}</td>
        <td>${slotLabel(row.slot)}</td>
        <td>${row.theme}</td>
        <td class="draft-cell">${
          row.refresh_mode === "jit_noon"
            ? "投稿30分前に自動生成（AIニュース要約 + 予測 + 行動, リンクなし）"
            : row.text
        }</td>
        <td class="plan-media-cell">
          <div class="plan-media-status">${esc(planMediaStatusLabel(row))}</div>
          ${
            row.media_url
              ? `<img class="plan-media-preview plan-media-zoomable" src="${esc(row.media_url)}" alt="plan generated media" />`
              : `<div class="plan-media-empty">${canPlanGenerateImage(row.slot) ? "画像なし" : "昼枠は画像なし"}</div>`
          }
          <div class="op-progress plan-media-progress${row.media_generating ? " show" : ""}">
            <div class="op-progress-bar">
              <i style="width:${row.media_generating ? "2%" : "0%"}"></i>
            </div>
            <p>${row.media_generating ? "生成中 0%" : "待機中"}</p>
          </div>
          ${
            canPlanGenerateImage(row.slot)
              ? `
            <div class="plan-media-actions">
              <select class="visual-mode-select plan-visual-mode">
                ${buildVisualModeOptions(row.media_visual_mode || "auto")}
              </select>
              <button type="button" class="ghost mini plan-generate-image">${
                row.media_path ? "やり直し" : "Nano Banana Proで生成"
              }</button>
              <button type="button" class="ghost mini plan-approve-image"${
                row.media_path ? "" : " disabled"
              }>${row.media_approved ? "添付OK" : "OKで添付"}</button>
              <button type="button" class="ghost mini plan-clear-image"${
                row.media_path ? "" : " disabled"
              }>解除</button>
            </div>
          `
              : ""
          }
        </td>
      </tr>
    `,
    )
    .join("");
  planTbody.innerHTML = html;
}

function renderQueueRows(items) {
  if (!items.length) {
    queueTbody.innerHTML = "<tr><td colspan='7'>保存された投稿キューはありません。</td></tr>";
    return;
  }
  const html = items
    .map(
      (row, idx) => `
      <tr data-idx="${idx}" data-refresh-mode="${esc(row.refresh_mode || "")}" data-slot="${esc(row.slot || "")}">
        <td><input type="checkbox" class="queue-select" /></td>
        <td><input type="datetime-local" class="queue-datetime" value="${esc(row.schedule_at)}" /></td>
        <td>${esc(slotLabel(row.slot))}</td>
        <td>${esc(row.theme || "")}</td>
        <td>
          <textarea class="queue-text" placeholder="${
            row.refresh_mode === "jit_noon" ? "投稿30分前に自動生成されます（手動入力も可）" : ""
          }">${esc(row.text || "")}</textarea>
        </td>
        <td>
          <textarea class="queue-reply-text" placeholder="投稿後に付けるリプ（任意）">${esc(row.reply_text || "")}</textarea>
        </td>
        <td class="queue-media-cell" data-media-path="${esc(row.media_path || "")}">
          <div class="queue-media-meta">
            ${
              row.media_url
                ? `<a class="queue-media-link" href="${esc(row.media_url)}" target="_blank" rel="noreferrer">${esc(
                    row.media_name || "添付画像",
                  )}</a>`
                : `<span class="queue-media-empty">未添付</span>`
            }
          </div>
          <div class="queue-media-actions">
            <input type="file" class="queue-media-file" accept=".png,.jpg,.jpeg,.webp,.gif" />
            <button type="button" class="ghost mini queue-media-upload">画像を添付</button>
            <button type="button" class="ghost mini queue-media-clear"${
              row.media_path ? "" : " disabled"
            }>解除</button>
          </div>
        </td>
      </tr>
    `,
    )
    .join("");
  queueTbody.innerHTML = html;
}

function applyPlanToQueue() {
  if (!currentPlan.length) {
    queueMessage.textContent = "先に投稿計画を作成してください。";
    return;
  }
  currentQueue = currentPlan.map((p) => ({
    schedule_at: toDateTimeLocal(p.date, p.time),
    slot: p.slot,
    theme: p.theme,
    text: p.refresh_mode === "jit_noon" ? "" : p.text,
    reply_text: "",
    media_path: p.media_approved ? p.media_path || "" : "",
    media_name: p.media_approved ? p.media_name || "" : "",
    media_url: p.media_approved ? p.media_url || "" : "",
    refresh_mode: p.refresh_mode || "",
  }));
  renderQueueRows(currentQueue);
  queueMessage.textContent = `${currentQueue.length}件を投稿キューに反映しました。`;
  showButtonSuccess(document.getElementById("applyPlanToQueueBtn"));
}

async function generatePlanImage(idx) {
  const row = currentPlan[idx];
  if (!row || !canPlanGenerateImage(row.slot)) return;
  const tr = planTbody.querySelector(`tr[data-plan-idx="${idx}"]`);
  const progressWrap = tr?.querySelector(".plan-media-progress");
  const progressBar = progressWrap?.querySelector("i");
  const progressText = progressWrap?.querySelector("p");
  const generateBtn = tr?.querySelector(".plan-generate-image");
  const approveBtn = tr?.querySelector(".plan-approve-image");
  const clearBtn = tr?.querySelector(".plan-clear-image");
  currentPlan[idx] = normalizePlanItem({ ...row, media_generating: true });
  planMessage.textContent = `${slotLabel(row.slot)}枠の画像を生成中...`;
  if (generateBtn) generateBtn.setAttribute("disabled", "disabled");
  if (approveBtn) approveBtn.setAttribute("disabled", "disabled");
  if (clearBtn) clearBtn.setAttribute("disabled", "disabled");
  const progress =
    progressWrap && progressBar && progressText
      ? startInlineProgress("plan_image", progressWrap, progressBar, progressText, 18000)
      : null;
  try {
    const data = await fetchJson("/api/generate_image", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: row.text, visual_mode: row.media_visual_mode || getDefaultVisualMode() }),
    });
    currentPlan[idx] = normalizePlanItem({
      ...row,
      media_path: data.path || "",
      media_url: data.url || "",
      media_name: (data.path || "").split("/").pop() || "generated.png",
      media_approved: false,
      media_generating: false,
    });
    progress?.done(true);
    renderPlanRows(currentPlan);
    planMessage.textContent = `${slotLabel(row.slot)}枠の画像を生成しました。問題なければ「OKで添付」を押してください。`;
    showButtonSuccess(generateBtn);
  } catch (e) {
    currentPlan[idx] = normalizePlanItem({ ...row, media_generating: false });
    progress?.done(false);
    renderPlanRows(currentPlan);
    planMessage.textContent = `画像生成エラー: ${e}`;
  }
}

function approvePlanImage(idx) {
  const row = currentPlan[idx];
  if (!row || !row.media_path) return;
  currentPlan[idx] = normalizePlanItem({ ...row, media_approved: true });
  renderPlanRows(currentPlan);
  planMessage.textContent = `${slotLabel(row.slot)}枠の画像を添付予定にしました。`;
  const btn = planTbody.querySelector(`tr[data-plan-idx="${idx}"] .plan-approve-image`);
  showButtonSuccess(btn);
}

function clearPlanImage(idx) {
  const row = currentPlan[idx];
  if (!row) return;
  currentPlan[idx] = normalizePlanItem({
    ...row,
    media_path: "",
    media_url: "",
    media_name: "",
    media_approved: false,
    media_generating: false,
  });
  renderPlanRows(currentPlan);
  planMessage.textContent = `${slotLabel(row.slot)}枠の画像を解除しました。`;
  const btn = planTbody.querySelector(`tr[data-plan-idx="${idx}"] .plan-clear-image`);
  showButtonSuccess(btn);
}

function collectQueueFromTable() {
  const rows = [...queueTbody.querySelectorAll("tr[data-idx]")];
  const out = [];
  rows.forEach((tr) => {
    const datetime = tr.querySelector(".queue-datetime")?.value || "";
    const text = (tr.querySelector(".queue-text")?.value || "").trim();
    const replyText = (tr.querySelector(".queue-reply-text")?.value || "").trim();
    const refreshMode = tr.dataset.refreshMode || "";
    const cells = tr.querySelectorAll("td");
    const slot = (tr.dataset.slot || "").trim();
    const theme = cells[3]?.textContent?.trim() || "";
    const mediaCell = tr.querySelector(".queue-media-cell");
    const mediaPath = mediaCell?.dataset.mediaPath || "";
    if (datetime && slot) {
      out.push({
        schedule_at: datetime,
        slot,
        theme,
        text,
        reply_text: replyText,
        media_path: mediaPath,
        refresh_mode: refreshMode,
      });
    }
  });
  return out;
}

function syncQueueFromTable() {
  const rows = [...queueTbody.querySelectorAll("tr[data-idx]")];
  if (!rows.length) return currentQueue;
  currentQueue = rows
    .map((tr) => {
      const idx = Number(tr.dataset.idx);
      const prev = currentQueue[idx] || {};
      const datetime = tr.querySelector(".queue-datetime")?.value || "";
      const text = (tr.querySelector(".queue-text")?.value || "").trim();
      const replyText = (tr.querySelector(".queue-reply-text")?.value || "").trim();
      const refreshMode = tr.dataset.refreshMode || "";
      const slot = (tr.dataset.slot || "").trim();
      const cells = tr.querySelectorAll("td");
      const theme = cells[3]?.textContent?.trim() || "";
      const mediaCell = tr.querySelector(".queue-media-cell");
      const mediaPath = mediaCell?.dataset.mediaPath || prev.media_path || "";
      if (!datetime || !slot) return null;
      return {
        ...prev,
        schedule_at: datetime,
        slot,
        theme,
        text,
        reply_text: replyText,
        media_path: mediaPath,
        refresh_mode: refreshMode,
      };
    })
    .filter(Boolean);
  return currentQueue;
}

async function buildPlan() {
  planMessage.textContent = "計画を作成中...";
  planTbody.innerHTML = "";
  const p = startProgress("plan", planProgressWrap, planProgressBar, planProgressText, 8000);
  try {
    planGenerationNonce += 1;
    const data = await fetchJson("/api/plan_preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        unit: planUnit.value,
        count: Number(planCount.value || 1),
        every_day: !!planEveryDay.checked,
        start_date: planStartDate.value,
        generation_nonce: planGenerationNonce,
      }),
    });
    planGenerationNonce = Number(data.generation_nonce || planGenerationNonce);
    planMessage.textContent = `${data.count}件の投稿予定を作成しました。`;
    currentPlan = (data.plan || []).map(normalizePlanItem);
    renderPlanRows(currentPlan);
    p.done(true);
    showButtonSuccess(document.getElementById("buildPlanBtn"));
  } catch (e) {
    planMessage.textContent = `計画作成エラー: ${e}`;
    p.done(false);
  }
}

async function saveQueue() {
  const queue = syncQueueFromTable();
  queueMessage.textContent = "キュー保存中...";
  try {
    const data = await fetchJson("/api/queue", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ queue }),
    });
    currentQueue = data.queue || queue;
    renderQueueRows(currentQueue);
    queueMessage.textContent = data.message || "キューを保存しました。";
    showButtonSuccess(document.getElementById("saveQueueBtn"));
  } catch (e) {
    queueMessage.textContent = `キュー保存エラー: ${e}`;
  }
}

async function loadQueue() {
  queueMessage.textContent = "キュー読込中...";
  try {
    const data = await fetchJson("/api/queue");
    currentQueue = (data.queue || []).map((q) => {
      const legacyNoonRuleText =
        typeof q.text === "string" &&
        q.text.includes("昼枠は最新AI情報の引用シェア。動画付き投稿を優先し、無ければ画像付きから選びます。");
      if (q.slot === "noon" && legacyNoonRuleText && !q.refresh_mode) {
        return { ...q, text: "", refresh_mode: "jit_noon" };
      }
      return q;
    });
    renderQueueRows(currentQueue);
    queueMessage.textContent = `${currentQueue.length}件のキューを読み込みました。`;
    showButtonSuccess(document.getElementById("loadQueueBtn"));
  } catch (e) {
    queueMessage.textContent = `キュー読込エラー: ${e}`;
  }
}

function deleteSelectedQueueRows() {
  syncQueueFromTable();
  const rows = [...queueTbody.querySelectorAll("tr[data-idx]")];
  const selectedIdx = rows
    .filter((tr) => tr.querySelector(".queue-select")?.checked)
    .map((tr) => Number(tr.dataset.idx));
  if (!selectedIdx.length) {
    queueMessage.textContent = "削除対象を選択してください。";
    return;
  }
  currentQueue = currentQueue.filter((_, idx) => !selectedIdx.includes(idx));
  renderQueueRows(currentQueue);
  queueMessage.textContent = `${selectedIdx.length}件をキューから外しました。保存すると反映されます。`;
  showButtonSuccess(deleteSelectedQueueBtn);
}

function clearQueueRows() {
  currentQueue = [];
  renderQueueRows(currentQueue);
  queueMessage.textContent = "キューを空にしました。保存すると反映されます。";
  showButtonSuccess(clearQueueBtn);
}

async function uploadQueueMedia(idx, file) {
  syncQueueFromTable();
  if (!file) {
    queueMessage.textContent = "添付する画像を選択してください。";
    return;
  }
  queueMessage.textContent = "画像をアップロード中...";
  const form = new FormData();
  form.append("media", file);
  try {
    const data = await fetchFormJson("/api/queue_media_upload", form);
    currentQueue[idx] = {
      ...currentQueue[idx],
      media_path: data.media_path || "",
      media_url: data.media_url || "",
      media_name: data.media_name || "",
    };
    renderQueueRows(currentQueue);
    queueMessage.textContent = data.message || "画像を添付しました。保存すると反映されます。";
    const btn = queueTbody.querySelector(`tr[data-idx="${idx}"] .queue-media-upload`);
    showButtonSuccess(btn);
  } catch (e) {
    queueMessage.textContent = `画像添付エラー: ${e}`;
  }
}

function clearQueueMedia(idx) {
  syncQueueFromTable();
  currentQueue[idx] = {
    ...currentQueue[idx],
    media_path: "",
    media_url: "",
    media_name: "",
  };
  renderQueueRows(currentQueue);
  queueMessage.textContent = "添付画像を解除しました。保存すると反映されます。";
  const btn = queueTbody.querySelector(`tr[data-idx="${idx}"] .queue-media-clear`);
  showButtonSuccess(btn);
}

cards.forEach((card) => {
  card.addEventListener("click", () => {
    cards.forEach((c) => c.classList.remove("active"));
    card.classList.add("active");
    setPreview(card.dataset.slot);
  });
});

const pageMeta = {
  dashboard: "ダッシュボード",
  generation: "投稿生成",
  planner: "投稿計画",
  queue: "投稿キュー",
  settings: "設定",
};

function setPage(page) {
  if (!pageMeta[page]) page = "dashboard";
  currentPage = page;
  pageCards.forEach((card) => {
    const p = card.dataset.page;
    if (p === page) {
      card.classList.remove("page-hidden");
    } else {
      card.classList.add("page-hidden");
    }
  });
  topPageButtons.forEach((b) => b.classList.toggle("active", b.dataset.page === page));
  railPageButtons.forEach((b) => b.classList.toggle("active", b.dataset.page === page));
  railHint.textContent = pageMeta[page] || "";
  localStorage.setItem("ui_current_page", page);
}

topPageButtons.forEach((btn) => {
  btn.addEventListener("click", () => setPage(btn.dataset.page || "dashboard"));
});

railPageButtons.forEach((btn) => {
  btn.addEventListener("click", () => setPage(btn.dataset.page || "dashboard"));
});

document.getElementById("checkAccountBtn").addEventListener("click", checkAccount);
document.getElementById("refreshBtn").addEventListener("click", checkAccount);
document.getElementById("runSelectedBtn").addEventListener("click", () => runDry(selectedSlot));
document.getElementById("runThisBtn").addEventListener("click", () => runDry(selectedSlot));
document.getElementById("generateDraftBtn").addEventListener("click", generateDraft);
document.getElementById("generateImageBtn").addEventListener("click", generateImageFromDraft);
document.getElementById("reloadEnvBtn").addEventListener("click", loadEnvStatus);
document.getElementById("saveEnvBtn").addEventListener("click", saveEnv);
document.getElementById("saveMediaBtn").addEventListener("click", saveMediaConfig);
document.getElementById("uploadPdfBtn").addEventListener("click", uploadPdf);
document.getElementById("reloadPdfBtn").addEventListener("click", loadPdfLibrary);
document.getElementById("buildPlanBtn").addEventListener("click", buildPlan);
document.getElementById("testPostBtn").addEventListener("click", testPost);
document.getElementById("saveTargetBtn").addEventListener("click", saveTargetAccount);
document.getElementById("verifyTargetBtn").addEventListener("click", verifyTargetAccount);
document.getElementById("applyPlanToQueueBtn").addEventListener("click", applyPlanToQueue);
document.getElementById("saveQueueBtn").addEventListener("click", saveQueue);
document.getElementById("loadQueueBtn").addEventListener("click", loadQueue);
deleteSelectedQueueBtn?.addEventListener("click", deleteSelectedQueueRows);
clearQueueBtn?.addEventListener("click", clearQueueRows);

planTbody.addEventListener("click", async (ev) => {
  const target = ev.target;
  if (!(target instanceof HTMLElement)) return;
  const zoomImage = target.closest(".plan-media-zoomable");
  if (zoomImage instanceof HTMLImageElement) {
    openImageInWindow(getModalImageSrc(zoomImage));
    return;
  }
  const tr = target.closest("tr[data-plan-idx]");
  if (!tr) return;
  const idx = Number(tr.dataset.planIdx);
  if (!Number.isFinite(idx)) return;
  if (target.classList.contains("plan-generate-image")) {
    await generatePlanImage(idx);
    return;
  }
  if (target.classList.contains("plan-approve-image")) {
    approvePlanImage(idx);
    return;
  }
  if (target.classList.contains("plan-clear-image")) {
    clearPlanImage(idx);
  }
});

generatedMediaPreview?.addEventListener("click", () => {
  if (!generatedMediaPreview.classList.contains("show")) return;
  openImageInWindow(getModalImageSrc(generatedMediaPreview));
});

planTbody.addEventListener("change", (ev) => {
  const target = ev.target;
  if (!(target instanceof HTMLSelectElement) || !target.classList.contains("plan-visual-mode")) return;
  const tr = target.closest("tr[data-plan-idx]");
  if (!tr) return;
  const idx = Number(tr.dataset.planIdx);
  const row = currentPlan[idx];
  if (!row) return;
  currentPlan[idx] = normalizePlanItem({ ...row, media_visual_mode: target.value || "auto" });
  planMessage.textContent = `${slotLabel(row.slot)}枠の画像モードを更新しました。`;
});

document.querySelectorAll(".slot-run").forEach((btn) => {
  btn.addEventListener("click", () => runDry(btn.dataset.slot));
});

previewEditor.addEventListener("input", () => {
  updateXPreview(previewEditor.value);
});
planUnit.addEventListener("change", updateCountSelector);

queueTbody.addEventListener("input", (ev) => {
  const target = ev.target;
  if (!(target instanceof HTMLTextAreaElement)) return;
  if (!target.classList.contains("queue-text") && !target.classList.contains("queue-reply-text")) return;
  if (!target.classList.contains("queue-text")) return;
  previewEditor.value = target.value;
  updateXPreview(previewEditor.value);
});

queueTbody.addEventListener("click", async (ev) => {
  const target = ev.target;
  if (!(target instanceof HTMLElement)) return;
  const tr = target.closest("tr[data-idx]");
  if (!tr) return;
  const idx = Number(tr.dataset.idx);
  if (target.classList.contains("queue-media-upload")) {
    const fileInput = tr.querySelector(".queue-media-file");
    const file = fileInput?.files?.[0];
    await uploadQueueMedia(idx, file);
    return;
  }
  if (target.classList.contains("queue-media-clear")) {
    clearQueueMedia(idx);
  }
});

if (pdfListBody) {
  pdfListBody.addEventListener("click", (ev) => {
    const target = ev.target;
    if (!(target instanceof HTMLElement)) return;
    const saveBtn = target.closest(".pdf-save-btn");
    if (saveBtn) {
      const docId = saveBtn.getAttribute("data-pdf-id") || "";
      if (!docId) return;
      const tr = saveBtn.closest("tr");
      if (!tr) return;
      const priority = tr.querySelector(".pdf-priority")?.value || "3";
      const scope = tr.querySelector(".pdf-scope")?.value || "all";
      updatePdfSettings(docId, priority, scope);
      return;
    }
    const btn = target.closest(".pdf-delete-btn");
    if (!btn) return;
    const docId = btn.getAttribute("data-pdf-id") || "";
    if (!docId) return;
    deletePdf(docId);
  });
}

setPreview(selectedSlot);
planStartDate.value = new Date().toISOString().slice(0, 10);
updateCountSelector();
planCount.value = "7";
loadEnvStatus();
loadMediaConfig();
loadPdfLibrary();
loadTargetAccount();
loadQueue();
setPage(localStorage.getItem("ui_current_page") || "dashboard");

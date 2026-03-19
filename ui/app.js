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
const queueTodayCount = document.getElementById("queueTodayCount");
const queueRemainingCount = document.getElementById("queueRemainingCount");
const queuePostedCount = document.getElementById("queuePostedCount");
const analyticsDays = document.getElementById("analyticsDays");
const analyticsSlotFilter = document.getElementById("analyticsSlotFilter");
const analyticsTypeFilter = document.getElementById("analyticsTypeFilter");
const analyticsSourceFilter = document.getElementById("analyticsSourceFilter");
const analyticsMediaFilter = document.getElementById("analyticsMediaFilter");
const analyticsSort = document.getElementById("analyticsSort");
const analyticsMessage = document.getElementById("analyticsMessage");
const analyticsCount = document.getElementById("analyticsCount");
const analyticsAvgImpressions = document.getElementById("analyticsAvgImpressions");
const analyticsAvgEngagement = document.getElementById("analyticsAvgEngagement");
const analyticsBestPost = document.getElementById("analyticsBestPost");
const analyticsWorstPost = document.getElementById("analyticsWorstPost");
const analyticsSlotCompare = document.getElementById("analyticsSlotCompare");
const analyticsTypeCompare = document.getElementById("analyticsTypeCompare");
const analyticsLengthCompare = document.getElementById("analyticsLengthCompare");
const analyticsMediaCompare = document.getElementById("analyticsMediaCompare");
const analyticsSourceCompare = document.getElementById("analyticsSourceCompare");
const analyticsList = document.getElementById("analyticsList");
const analyticsDetailModal = document.getElementById("analyticsDetailModal");
const analyticsDetailMeta = document.getElementById("analyticsDetailMeta");
const analyticsDetailBody = document.getElementById("analyticsDetailBody");
const analyticsDetailCloseBtn = document.getElementById("analyticsDetailCloseBtn");
const railHint = document.getElementById("railHint");
const generateImageBtn = document.getElementById("generateImageBtn");
const deleteSelectedQueueBtn = document.getElementById("deleteSelectedQueueBtn");
const clearQueueBtn = document.getElementById("clearQueueBtn");
const imageModal = document.getElementById("imageModal");
const imageModalPreview = document.getElementById("imageModalPreview");
const imageModalCloseBtn = document.getElementById("imageModalCloseBtn");

let currentPlan = [];
let currentQueue = [];
let analyticsItems = [];
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

function normalizeQueueItem(item) {
  const hasFinalMedia = !!(item.media_path || item.media_url);
  const source = (item.media_source || (hasFinalMedia ? "existing" : "none")).trim() || "none";
  return {
    ...item,
    media_source: source,
    media_prompt: item.media_prompt || "",
    media_visual_mode: item.media_visual_mode || getDefaultVisualMode(),
    media_path: item.media_path || "",
    media_url: item.media_url || "",
    media_name: item.media_name || "",
    media_candidate_path: item.media_candidate_path || "",
    media_candidate_url: item.media_candidate_url || "",
    media_candidate_name: item.media_candidate_name || "",
    media_generating: !!item.media_generating,
  };
}

function formatQueueDateTime(value) {
  const raw = String(value || "").trim();
  if (!raw) return "未設定";
  const [datePart = "", timePart = ""] = raw.replace("T", " ").split(" ");
  return timePart ? `${datePart} / ${timePart.slice(0, 5)}` : datePart;
}

function formatMetricNumber(value) {
  const num = Number(value || 0);
  if (!Number.isFinite(num)) return "0";
  return new Intl.NumberFormat("ja-JP").format(Math.round(num));
}

function formatPercent(value) {
  const num = Number(value || 0);
  if (!Number.isFinite(num)) return "0%";
  return `${num.toFixed(2)}%`;
}

function analyticsLabel(kind, key) {
  const maps = {
    slot: { morning: "Morning", noon: "Noon", evening: "Evening", manual: "Manual", "-": "-" },
    content_type: { design: "design", news: "news", quote: "quote", manual: "manual", "-": "-" },
    length_bucket: { short: "短文", medium: "中短文", long: "長文", xlong: "超長文", "-": "-" },
    has_media: { media: "mediaあり", no_media: "mediaなし", "-": "-" },
    source: { auto: "auto", queue: "queue", manual: "manual", "-": "-" },
  };
  return (maps[kind] && maps[kind][key]) || key || "-";
}

function queueStatusLabel(row) {
  if (row.posted || row.status === "posted") return "投稿済み";
  if (row.refresh_mode === "jit_noon" && !(row.text || "").trim()) return "直前生成";
  return "予約中";
}

function queueStatusClass(row) {
  if (row.posted || row.status === "posted") return "posted";
  if (row.refresh_mode === "jit_noon" && !(row.text || "").trim()) return "dynamic";
  return "scheduled";
}

function queueSectionMeta(slot) {
  if (slot === "morning") return { title: "Morning", lead: "学びと設計視点を積み上げる朝枠" };
  if (slot === "noon") return { title: "Noon", lead: "AIニュースと予測を扱う昼枠" };
  return { title: "Evening", lead: "共感と振り返りを整える夕方枠" };
}

function updateQueueKpis(items) {
  const today = new Date().toISOString().slice(0, 10);
  const todayCount = items.filter((item) => String(item.schedule_at || "").slice(0, 10) === today).length;
  const remainingCount = items.filter((item) => !(item.posted || item.status === "posted")).length;
  const postedCount = items.filter((item) => item.posted || item.status === "posted").length;
  if (queueTodayCount) queueTodayCount.textContent = String(todayCount);
  if (queueRemainingCount) queueRemainingCount.textContent = String(remainingCount);
  if (queuePostedCount) queuePostedCount.textContent = String(postedCount);
}

function renderCompareList(target, kind, rows) {
  if (!target) return;
  if (!rows || !rows.length) {
    target.innerHTML = `<p class="helper">まだデータがありません。</p>`;
    return;
  }
  target.innerHTML = rows
    .map(
      (row) => `
        <article class="analytics-compare-item">
          <div>
            <strong>${esc(analyticsLabel(kind, row.key))}</strong>
            <small>${formatMetricNumber(row.count)}件</small>
          </div>
          <div class="analytics-compare-metrics">
            <span>Imp ${formatMetricNumber(row.avg_impressions)}</span>
            <span>ER ${formatPercent(row.avg_engagement_rate)}</span>
          </div>
        </article>
      `,
    )
    .join("");
}

function renderAnalyticsSummary(summary) {
  if (!summary) return;
  if (analyticsCount) analyticsCount.textContent = formatMetricNumber(summary.last30_posts);
  if (analyticsAvgImpressions) analyticsAvgImpressions.textContent = formatMetricNumber(summary.avg_impressions);
  if (analyticsAvgEngagement) analyticsAvgEngagement.textContent = formatPercent(summary.avg_engagement_rate);
  if (analyticsBestPost) {
    analyticsBestPost.textContent = summary.best_post
      ? `${formatPercent(summary.best_post.engagement_rate)} / ${summary.best_post.slot || "-"}`
      : "-";
  }
  if (analyticsWorstPost) {
    analyticsWorstPost.textContent = summary.worst_post
      ? `${formatPercent(summary.worst_post.engagement_rate)} / ${summary.worst_post.slot || "-"}`
      : "-";
  }
}

function openAnalyticsDetail(item) {
  if (!analyticsDetailModal || !analyticsDetailMeta || !analyticsDetailBody) return;
  analyticsDetailMeta.textContent = `${item.posted_at || "-"} / ${item.slot || "-"} / ${item.content_type || "-"}`;
  analyticsDetailBody.innerHTML = `
    <article class="analytics-detail-card">
      <div class="analytics-detail-text">${esc(item.cleaned_text || item.text || "").replaceAll("\n", "<br />")}</div>
      <div class="analytics-detail-grid">
        <div><span>Imp</span><strong>${formatMetricNumber(item.impressions)}</strong></div>
        <div><span>Like</span><strong>${formatMetricNumber(item.likes)}</strong></div>
        <div><span>Repost</span><strong>${formatMetricNumber(item.reposts)}</strong></div>
        <div><span>Reply</span><strong>${formatMetricNumber(item.replies)}</strong></div>
        <div><span>Bookmark</span><strong>${formatMetricNumber(item.bookmarks)}</strong></div>
        <div><span>ER</span><strong>${formatPercent(item.engagement_rate)}</strong></div>
      </div>
      <div class="analytics-attr-grid">
        <div><span>source</span><strong>${esc(item.source || "-")}</strong></div>
        <div><span>pattern</span><strong>${esc(item.pattern_type || "-")}</strong></div>
        <div><span>topic</span><strong>${esc(item.topic || "-")}</strong></div>
        <div><span>claim</span><strong>${esc(item.claim || "-")}</strong></div>
        <div><span>structure</span><strong>${esc(item.structure || "-")}</strong></div>
        <div><span>media</span><strong>${item.has_media ? "あり" : "なし"}</strong></div>
      </div>
    </article>
  `;
  analyticsDetailModal.classList.add("show");
  analyticsDetailModal.setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-open");
}

function closeAnalyticsDetail() {
  if (!analyticsDetailModal) return;
  analyticsDetailModal.classList.remove("show");
  analyticsDetailModal.setAttribute("aria-hidden", "true");
  document.body.classList.remove("modal-open");
}

function renderAnalyticsList(items) {
  if (!analyticsList) return;
  if (!items.length) {
    analyticsList.innerHTML = `<p class="helper">条件に合う投稿がありません。</p>`;
    return;
  }
  analyticsList.innerHTML = items
    .map(
      (item) => `
        <article class="analytics-post-card" data-tweet-id="${esc(item.tweet_id)}">
          <div class="analytics-post-top">
            <div class="analytics-post-meta">
              <span>${esc(item.posted_at || "-")}</span>
              <span>${esc(item.slot || "-")}</span>
              <span>${esc(item.content_type || "-")}</span>
              <span>${esc(item.source || "-")}</span>
              <span>${item.has_media ? "media" : "text"}</span>
            </div>
            <div class="analytics-post-stats">
              <strong>Imp ${formatMetricNumber(item.impressions)}</strong>
              <span>ER ${formatPercent(item.engagement_rate)}</span>
            </div>
          </div>
          <p class="analytics-post-text">${esc(item.text_preview || "")}</p>
          <div class="analytics-post-bottom">
            <span>Like ${formatMetricNumber(item.likes)}</span>
            <span>Repost ${formatMetricNumber(item.reposts)}</span>
            <span>Reply ${formatMetricNumber(item.replies)}</span>
            <span>Bookmark ${formatMetricNumber(item.bookmarks)}</span>
          </div>
        </article>
      `,
    )
    .join("");
}

async function loadAnalytics() {
  if (!analyticsMessage) return;
  analyticsMessage.textContent = "分析データを読み込み中...";
  try {
    const params = new URLSearchParams({
      days: analyticsDays?.value || "30",
      slot: analyticsSlotFilter?.value || "",
      content_type: analyticsTypeFilter?.value || "",
      source: analyticsSourceFilter?.value || "",
      has_media: analyticsMediaFilter?.value || "",
      sort: analyticsSort?.value || "posted_at_desc",
    });
    const data = await fetchJson(`/api/analytics?${params.toString()}`);
    analyticsItems = data.items || [];
    renderAnalyticsSummary(data.summary || {});
    renderCompareList(analyticsSlotCompare, "slot", data.comparisons?.slot || []);
    renderCompareList(analyticsTypeCompare, "content_type", data.comparisons?.content_type || []);
    renderCompareList(analyticsLengthCompare, "length_bucket", data.comparisons?.length_bucket || []);
    renderCompareList(analyticsMediaCompare, "has_media", data.comparisons?.has_media || []);
    renderCompareList(analyticsSourceCompare, "source", data.comparisons?.source || []);
    renderAnalyticsList(analyticsItems);
    analyticsMessage.textContent = `${formatMetricNumber(analyticsItems.length)}件の投稿を表示しています。`;
  } catch (e) {
    analyticsMessage.textContent = `分析読み込みエラー: ${e}`;
  }
}

async function refreshAnalytics() {
  if (!analyticsMessage) return;
  analyticsMessage.textContent = "Xから最新 metrics を更新中...";
  try {
    const data = await fetchJson("/api/analytics/refresh", { method: "POST" });
    analyticsMessage.textContent = data.message || "metrics を更新しました。";
    showButtonSuccess(document.getElementById("analyticsRefreshBtn"));
    await loadAnalytics();
  } catch (e) {
    analyticsMessage.textContent = `metrics 更新エラー: ${e}`;
  }
}

function planMediaStatusLabel(row) {
  if (!canPlanGenerateImage(row.slot)) return "対象外";
  if (row.media_generating) return "生成中";
  if (row.media_approved && row.media_path) return "添付予定";
  if (row.media_path) return "生成済み";
  return "未生成";
}

function queueMediaStatusLabel(row) {
  if (row.media_source === "generate" && row.media_path) return "生成画像を採用中";
  if (row.media_source === "existing" && row.media_path) return "既存画像を添付中";
  if (row.media_candidate_path) return "生成候補あり";
  if (row.media_source === "generate" && row.media_generating) return "生成中";
  if (row.media_source === "generate") return "生成待ち";
  if (row.media_source === "existing") return row.media_path ? "画像選択済み" : "既存画像待ち";
  return "画像なし";
}

function getModalImageSrc(img) {
  if (!(img instanceof HTMLImageElement)) return "";
  return img.currentSrc || img.getAttribute("src") || "";
}

function openImageModal(src) {
  if (!src || !imageModal || !imageModalPreview) return;
  imageModalPreview.src = src;
  imageModal.classList.add("show");
  imageModal.setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-open");
}

function closeImageModal() {
  if (!imageModal || !imageModalPreview) return;
  imageModal.classList.remove("show");
  imageModal.setAttribute("aria-hidden", "true");
  imageModalPreview.src = "";
  document.body.classList.remove("modal-open");
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
  updateQueueKpis(items);
  if (!items.length) {
    queueTbody.innerHTML = `
      <section class="queue-slot-section is-empty">
        <div class="queue-slot-header">
          <div>
            <h3>投稿キューは空です</h3>
            <p>「計画を作成」から始めると、ここにカード形式で並びます。</p>
          </div>
        </div>
      </section>
    `;
    return;
  }
  const grouped = {
    morning: [],
    noon: [],
    evening: [],
  };
  items.forEach((row, idx) => {
    const slot = ["morning", "noon", "evening"].includes(row.slot) ? row.slot : "evening";
    grouped[slot].push({ row, idx });
  });
  const html = ["morning", "noon", "evening"]
    .map((slot) => {
      const meta = queueSectionMeta(slot);
      const cards = grouped[slot]
        .map(
          ({ row, idx }) => `
      <article class="queue-card" data-idx="${idx}" data-refresh-mode="${esc(row.refresh_mode || "")}" data-slot="${esc(
            row.slot || "",
          )}">
        <div class="queue-card-top">
          <div class="queue-card-slot slot-${esc(row.slot || slot)}">
            <span class="queue-slot-label">${esc(slotLabel(row.slot))}</span>
            <strong>${esc(meta.title)}</strong>
          </div>
          <span class="queue-status-pill ${queueStatusClass(row)}">${esc(queueStatusLabel(row))}</span>
        </div>
        <div class="queue-card-meta">
          <label>
            <span>予約時刻</span>
            <input type="datetime-local" class="queue-datetime" value="${esc(row.schedule_at_local || row.schedule_at)}" />
          </label>
          <div class="queue-theme-box">
            <span>テーマ</span>
            <strong>${esc(row.theme || "テーマ未設定")}</strong>
            <small>${esc(formatQueueDateTime(row.schedule_at_local || row.schedule_at))}</small>
          </div>
        </div>
        <div class="queue-card-body">
          <label class="queue-field queue-field-wide">
            <span>投稿本文</span>
            <textarea class="queue-text" placeholder="${
              row.refresh_mode === "jit_noon" ? "投稿30分前に自動生成されます（手動入力も可）" : ""
            }">${esc(row.text || "")}</textarea>
          </label>
          <label class="queue-field">
            <span>投稿後リプ</span>
            <textarea class="queue-reply-text" placeholder="投稿後に付けるリプ（任意）">${esc(
              row.reply_text || "",
            )}</textarea>
          </label>
        </div>
        <div class="queue-media-card queue-media-cell" data-media-path="${esc(row.media_path || "")}">
          <div class="queue-media-meta">
            <strong class="queue-media-status">${esc(queueMediaStatusLabel(row))}</strong>
            <select class="visual-mode-select queue-media-source">
              <option value="none"${row.media_source === "none" ? " selected" : ""}>画像なし</option>
              <option value="existing"${row.media_source === "existing" ? " selected" : ""}>既存画像を添付</option>
              <option value="generate"${row.media_source === "generate" ? " selected" : ""}>Nano Banana Proで生成</option>
            </select>
          </div>
          ${
            row.media_path || row.media_candidate_path
              ? `
            <div class="queue-media-preview-wrap">
              <img
                class="plan-media-preview queue-media-preview plan-media-zoomable"
                src="${esc(row.media_candidate_url || row.media_url || "")}"
                alt="queue media preview"
              />
              <div class="queue-media-caption">${
                row.media_candidate_path
                  ? `生成候補: ${esc(row.media_candidate_name || "generated.png")}`
                  : `採用中: ${esc(row.media_name || "添付画像")}`
              }</div>
            </div>
          `
              : `<div class="queue-media-empty">まだ画像は選ばれていません。</div>`
          }
          <div class="queue-media-panel${row.media_source === "existing" ? " show" : ""}" data-panel="existing">
            <div class="queue-media-actions">
              ${
                row.media_url
                  ? `<a class="queue-media-link" href="${esc(row.media_url)}" target="_blank" rel="noreferrer">${esc(
                      row.media_name || "添付画像",
                    )}</a>`
                  : `<span class="queue-media-empty">ローカル画像を選ぶか、保存済みの添付画像をそのまま使えます。</span>`
              }
              <input type="file" class="queue-media-file" accept=".png,.jpg,.jpeg,.webp,.gif" />
              <button type="button" class="ghost mini queue-media-upload">画像を添付</button>
              <button type="button" class="ghost mini queue-media-clear"${
                row.media_path ? "" : " disabled"
              }>解除</button>
            </div>
          </div>
          <div class="queue-media-panel${row.media_source === "generate" ? " show" : ""}" data-panel="generate">
            <div class="queue-media-actions">
              <textarea class="queue-media-prompt" placeholder="空欄なら投稿文をもとに画像プロンプトを組み立てます。">${esc(
                row.media_prompt || "",
              )}</textarea>
              <select class="visual-mode-select queue-media-visual-mode">
                ${buildVisualModeOptions(row.media_visual_mode || "auto")}
              </select>
              <div class="op-progress queue-media-progress${row.media_generating ? " show" : ""}">
                <div class="op-progress-bar">
                  <i style="width:${row.media_generating ? "2%" : "0%"}"></i>
                </div>
                <p>${row.media_generating ? "生成中 0%" : "待機中"}</p>
              </div>
              <button type="button" class="ghost mini queue-media-generate">${
                row.media_candidate_path ? "再生成" : "Nano Banana Proで生成"
              }</button>
              <button type="button" class="ghost mini queue-media-approve"${
                row.media_candidate_path ? "" : " disabled"
              }>採用</button>
              <button type="button" class="ghost mini queue-media-cancel"${
                row.media_candidate_path ? "" : " disabled"
              }>キャンセル</button>
            </div>
          </div>
        </div>
        <div class="queue-card-actions">
          <label class="queue-select-pill">
            <input type="checkbox" class="queue-select" />
            <span>選択</span>
          </label>
          <button type="button" class="ghost mini queue-edit-btn">
            <span class="material-symbols-rounded">edit</span>
            <span>編集</span>
          </button>
          <button type="button" class="ghost mini danger queue-delete-btn">
            <span class="material-symbols-rounded">delete</span>
            <span>削除</span>
          </button>
        </div>
      </article>
    `,
        )
        .join("");
      return `
        <section class="queue-slot-section">
          <div class="queue-slot-header">
            <div>
              <p class="queue-section-kicker">${esc(meta.title)}</p>
              <h3>${esc(slotLabel(slot))} セクション</h3>
              <p>${esc(meta.lead)}</p>
            </div>
            <span class="queue-slot-count">${grouped[slot].length}件</span>
          </div>
          <div class="queue-slot-grid${cards ? "" : " is-empty"}">
            ${
              cards ||
              `<div class="queue-empty-card"><strong>${esc(slotLabel(slot))}のキューはまだありません。</strong><p>この枠の予約を追加すると、ここに表示されます。</p></div>`
            }
          </div>
        </section>
      `;
    })
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
    media_source: p.media_approved ? "generate" : "none",
    media_prompt: p.text || "",
    media_visual_mode: p.media_visual_mode || getDefaultVisualMode(),
    media_path: p.media_approved ? p.media_path || "" : "",
    media_name: p.media_approved ? p.media_name || "" : "",
    media_url: p.media_approved ? p.media_url || "" : "",
    refresh_mode: p.refresh_mode || "",
  })).map(normalizeQueueItem);
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
  const rows = [...queueTbody.querySelectorAll("[data-idx]")];
  const out = [];
  rows.forEach((card) => {
    const datetime = card.querySelector(".queue-datetime")?.value || "";
    const text = (card.querySelector(".queue-text")?.value || "").trim();
    const replyText = (card.querySelector(".queue-reply-text")?.value || "").trim();
    const refreshMode = card.dataset.refreshMode || "";
    const slot = (card.dataset.slot || "").trim();
    const theme = card.querySelector(".queue-theme-box strong")?.textContent?.trim() || "";
    const mediaCell = card.querySelector(".queue-media-cell");
    const mediaPath = mediaCell?.dataset.mediaPath || "";
    const mediaSource = card.querySelector(".queue-media-source")?.value || "none";
    const mediaPrompt = (card.querySelector(".queue-media-prompt")?.value || "").trim();
    const mediaVisualMode = card.querySelector(".queue-media-visual-mode")?.value || getDefaultVisualMode();
    if (datetime && slot) {
      out.push({
        schedule_at: datetime,
        slot,
        theme,
        text,
        reply_text: replyText,
        media_source: mediaSource,
        media_prompt: mediaPrompt,
        media_visual_mode: mediaVisualMode,
        media_path: mediaPath,
        refresh_mode: refreshMode,
      });
    }
  });
  return out;
}

function syncQueueFromTable() {
  const rows = [...queueTbody.querySelectorAll("[data-idx]")];
  if (!rows.length) return currentQueue;
  currentQueue = rows
    .map((card) => {
      const idx = Number(card.dataset.idx);
      const prev = currentQueue[idx] || {};
      const datetime = card.querySelector(".queue-datetime")?.value || "";
      const text = (card.querySelector(".queue-text")?.value || "").trim();
      const replyText = (card.querySelector(".queue-reply-text")?.value || "").trim();
      const refreshMode = card.dataset.refreshMode || "";
      const slot = (card.dataset.slot || "").trim();
      const theme = card.querySelector(".queue-theme-box strong")?.textContent?.trim() || prev.theme || "";
      const mediaCell = card.querySelector(".queue-media-cell");
      const mediaPath = mediaCell?.dataset.mediaPath || prev.media_path || "";
      const mediaSource = card.querySelector(".queue-media-source")?.value || prev.media_source || "none";
      const mediaPrompt = (card.querySelector(".queue-media-prompt")?.value || prev.media_prompt || "").trim();
      const mediaVisualMode =
        card.querySelector(".queue-media-visual-mode")?.value || prev.media_visual_mode || getDefaultVisualMode();
      if (!datetime || !slot) return null;
      return normalizeQueueItem({
        ...prev,
        schedule_at: datetime,
        slot,
        theme,
        text,
        reply_text: replyText,
        media_source: mediaSource,
        media_prompt: mediaPrompt,
        media_visual_mode: mediaVisualMode,
        media_path: mediaPath,
        refresh_mode: refreshMode,
      });
    })
    .filter(Boolean);
  return currentQueue;
}

function updateQueueMediaSource(idx, source) {
  syncQueueFromTable();
  const row = currentQueue[idx];
  if (!row) return;
  if (source === "none") {
    currentQueue[idx] = normalizeQueueItem({
      ...row,
      media_source: "none",
      media_path: "",
      media_url: "",
      media_name: "",
      media_candidate_path: "",
      media_candidate_url: "",
      media_candidate_name: "",
      media_generating: false,
    });
  } else if (source === "existing") {
    currentQueue[idx] = normalizeQueueItem({
      ...row,
      media_source: "existing",
      media_candidate_path: "",
      media_candidate_url: "",
      media_candidate_name: "",
      media_generating: false,
    });
  } else {
    currentQueue[idx] = normalizeQueueItem({
      ...row,
      media_source: "generate",
      media_path: row.media_source === "generate" ? row.media_path : "",
      media_url: row.media_source === "generate" ? row.media_url : "",
      media_name: row.media_source === "generate" ? row.media_name : "",
    });
  }
  renderQueueRows(currentQueue);
}

async function generateQueueMedia(idx) {
  syncQueueFromTable();
  const row = currentQueue[idx];
  if (!row) return;
  const sourceText = (row.media_prompt || row.text || "").trim();
  if (!sourceText) {
    queueMessage.textContent = "画像生成には投稿文または生成用プロンプトが必要です。";
    return;
  }
  const card = queueTbody.querySelector(`[data-idx="${idx}"]`);
  const progressWrap = card?.querySelector(".queue-media-progress");
  const progressBar = progressWrap?.querySelector("i");
  const progressText = progressWrap?.querySelector("p");
  const generateBtn = card?.querySelector(".queue-media-generate");
  currentQueue[idx] = normalizeQueueItem({ ...row, media_source: "generate", media_generating: true });
  renderQueueRows(currentQueue);
  queueMessage.textContent = `${slotLabel(row.slot)}枠の画像を生成中...`;
  const refreshedCard = queueTbody.querySelector(`[data-idx="${idx}"]`);
  const nextProgressWrap = refreshedCard?.querySelector(".queue-media-progress");
  const nextProgressBar = nextProgressWrap?.querySelector("i");
  const nextProgressText = nextProgressWrap?.querySelector("p");
  const progress =
    nextProgressWrap && nextProgressBar && nextProgressText
      ? startInlineProgress("queue_image", nextProgressWrap, nextProgressBar, nextProgressText, 18000)
      : progressWrap && progressBar && progressText
        ? startInlineProgress("queue_image", progressWrap, progressBar, progressText, 18000)
        : null;
  try {
    const data = await fetchJson("/api/generate_image", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: sourceText, visual_mode: row.media_visual_mode || getDefaultVisualMode() }),
    });
    currentQueue[idx] = normalizeQueueItem({
      ...currentQueue[idx],
      media_source: "generate",
      media_generating: false,
      media_candidate_path: data.path || "",
      media_candidate_url: data.url || "",
      media_candidate_name: (data.path || "").split("/").pop() || "generated.png",
    });
    progress?.done(true);
    renderQueueRows(currentQueue);
    queueMessage.textContent = "画像を生成しました。内容を確認して「採用」を押してください。";
    showButtonSuccess(generateBtn);
  } catch (e) {
    currentQueue[idx] = normalizeQueueItem({ ...currentQueue[idx], media_generating: false });
    progress?.done(false);
    renderQueueRows(currentQueue);
    queueMessage.textContent = `画像生成エラー: ${e}`;
  }
}

function approveQueueGeneratedMedia(idx) {
  syncQueueFromTable();
  const row = currentQueue[idx];
  if (!row || !row.media_candidate_path) return;
  currentQueue[idx] = normalizeQueueItem({
    ...row,
    media_source: "generate",
    media_path: row.media_candidate_path,
    media_url: row.media_candidate_url,
    media_name: row.media_candidate_name,
    media_candidate_path: "",
    media_candidate_url: "",
    media_candidate_name: "",
  });
  renderQueueRows(currentQueue);
  queueMessage.textContent = "生成画像を投稿キューの添付画像として採用しました。";
  const btn = queueTbody.querySelector(`[data-idx="${idx}"] .queue-media-approve`);
  showButtonSuccess(btn);
}

function cancelQueueGeneratedMedia(idx) {
  syncQueueFromTable();
  const row = currentQueue[idx];
  if (!row) return;
  currentQueue[idx] = normalizeQueueItem({
    ...row,
    media_candidate_path: "",
    media_candidate_url: "",
    media_candidate_name: "",
    media_generating: false,
  });
  renderQueueRows(currentQueue);
  queueMessage.textContent = "生成候補をキャンセルしました。";
  const btn = queueTbody.querySelector(`[data-idx="${idx}"] .queue-media-cancel`);
  showButtonSuccess(btn);
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
    currentQueue = (data.queue || queue).map(normalizeQueueItem);
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
        return normalizeQueueItem({ ...q, text: "", refresh_mode: "jit_noon" });
      }
      return normalizeQueueItem(q);
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
  const rows = [...queueTbody.querySelectorAll("[data-idx]")];
  const selectedIdx = rows
    .filter((card) => card.querySelector(".queue-select")?.checked)
    .map((card) => Number(card.dataset.idx));
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
    currentQueue[idx] = normalizeQueueItem({
      ...currentQueue[idx],
      media_source: "existing",
      media_path: data.media_path || "",
      media_url: data.media_url || "",
      media_name: data.media_name || "",
      media_candidate_path: "",
      media_candidate_url: "",
      media_candidate_name: "",
    });
    renderQueueRows(currentQueue);
    queueMessage.textContent = data.message || "画像を添付しました。保存すると反映されます。";
    const btn = queueTbody.querySelector(`[data-idx="${idx}"] .queue-media-upload`);
    showButtonSuccess(btn);
  } catch (e) {
    queueMessage.textContent = `画像添付エラー: ${e}`;
  }
}

function clearQueueMedia(idx) {
  syncQueueFromTable();
  currentQueue[idx] = normalizeQueueItem({
    ...currentQueue[idx],
    media_source: "none",
    media_prompt: currentQueue[idx]?.media_prompt || "",
    media_path: "",
    media_url: "",
    media_name: "",
    media_candidate_path: "",
    media_candidate_url: "",
    media_candidate_name: "",
  });
  renderQueueRows(currentQueue);
  queueMessage.textContent = "添付画像を解除しました。保存すると反映されます。";
  const btn = queueTbody.querySelector(`[data-idx="${idx}"] .queue-media-clear`);
  showButtonSuccess(btn);
}

function deleteQueueCard(idx) {
  syncQueueFromTable();
  if (!Number.isFinite(idx)) return;
  currentQueue = currentQueue.filter((_, itemIdx) => itemIdx !== idx);
  renderQueueRows(currentQueue);
  queueMessage.textContent = "投稿カードを削除しました。保存すると反映されます。";
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
  analytics: "投稿分析",
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
  if (railHint) railHint.textContent = pageMeta[page] || "";
  localStorage.setItem("ui_current_page", page);
  if (page === "analytics") {
    loadAnalytics();
  }
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
document.getElementById("analyticsRefreshBtn")?.addEventListener("click", refreshAnalytics);
document.getElementById("queueHeroBuildBtn")?.addEventListener("click", () => {
  setPage("planner");
  document.getElementById("buildPlanBtn")?.click();
});
document.getElementById("queueHeroApplyBtn")?.addEventListener("click", () => {
  applyPlanToQueue();
  setPage("queue");
});
document.getElementById("saveQueueBtn").addEventListener("click", saveQueue);
document.getElementById("loadQueueBtn").addEventListener("click", loadQueue);
deleteSelectedQueueBtn?.addEventListener("click", deleteSelectedQueueRows);
clearQueueBtn?.addEventListener("click", clearQueueRows);
analyticsList?.addEventListener("click", (ev) => {
  const target = ev.target;
  if (!(target instanceof HTMLElement)) return;
  const card = target.closest(".analytics-post-card");
  if (!card) return;
  const tweetId = card.getAttribute("data-tweet-id") || "";
  const item = analyticsItems.find((row) => row.tweet_id === tweetId);
  if (item) openAnalyticsDetail(item);
});
analyticsDetailCloseBtn?.addEventListener("click", closeAnalyticsDetail);
analyticsDetailModal?.querySelector(".detail-modal-backdrop")?.addEventListener("click", closeAnalyticsDetail);
[
  analyticsDays,
  analyticsSlotFilter,
  analyticsTypeFilter,
  analyticsSourceFilter,
  analyticsMediaFilter,
  analyticsSort,
].forEach((el) => el?.addEventListener("change", () => loadAnalytics()));

planTbody.addEventListener("click", async (ev) => {
  const target = ev.target;
  if (!(target instanceof HTMLElement)) return;
  const zoomImage = target.closest(".plan-media-zoomable");
  if (zoomImage instanceof HTMLImageElement) {
    openImageModal(getModalImageSrc(zoomImage));
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
  openImageModal(getModalImageSrc(generatedMediaPreview));
});

imageModalCloseBtn?.addEventListener("click", closeImageModal);
imageModal?.querySelector(".image-modal-backdrop")?.addEventListener("click", closeImageModal);
imageModal?.addEventListener("click", (ev) => {
  if (ev.target === imageModal) closeImageModal();
});
document.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape" && imageModal?.classList.contains("show")) {
    closeImageModal();
  }
  if (ev.key === "Escape" && analyticsDetailModal?.classList.contains("show")) {
    closeAnalyticsDetail();
  }
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
  if (target.classList.contains("queue-text")) {
    previewEditor.value = target.value;
    updateXPreview(previewEditor.value);
  }
});

queueTbody.addEventListener("click", async (ev) => {
  const target = ev.target;
  if (!(target instanceof HTMLElement)) return;
  const zoomImage = target.closest(".queue-media-preview.plan-media-zoomable");
  if (zoomImage instanceof HTMLImageElement) {
    openImageModal(getModalImageSrc(zoomImage));
    return;
  }
  const card = target.closest("[data-idx]");
  if (!card) return;
  const idx = Number(card.dataset.idx);
  if (target.closest(".queue-edit-btn")) {
    card.querySelector(".queue-text")?.focus();
    return;
  }
  if (target.closest(".queue-delete-btn")) {
    deleteQueueCard(idx);
    return;
  }
  if (target.classList.contains("queue-media-upload")) {
    const fileInput = card.querySelector(".queue-media-file");
    const file = fileInput?.files?.[0];
    await uploadQueueMedia(idx, file);
    return;
  }
  if (target.classList.contains("queue-media-clear")) {
    clearQueueMedia(idx);
    return;
  }
  if (target.classList.contains("queue-media-generate")) {
    await generateQueueMedia(idx);
    return;
  }
  if (target.classList.contains("queue-media-approve")) {
    approveQueueGeneratedMedia(idx);
    return;
  }
  if (target.classList.contains("queue-media-cancel")) {
    cancelQueueGeneratedMedia(idx);
  }
});

queueTbody.addEventListener("change", (ev) => {
  const target = ev.target;
  if (!(target instanceof HTMLElement)) return;
  const card = target.closest("[data-idx]");
  if (!card) return;
  const idx = Number(card.dataset.idx);
  if (target instanceof HTMLSelectElement && target.classList.contains("queue-media-source")) {
    updateQueueMediaSource(idx, target.value || "none");
    return;
  }
  if (target instanceof HTMLSelectElement && target.classList.contains("queue-media-visual-mode")) {
    syncQueueFromTable();
    currentQueue[idx] = normalizeQueueItem({ ...currentQueue[idx], media_visual_mode: target.value || "auto" });
    return;
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

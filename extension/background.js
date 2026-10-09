const HOST = "artodownloader";
const bypass = new Set();
const interceptedUrls = new Set();

const DOWNLOAD_EXTS = new Set([
  "zip", "rar", "7z", "tar", "gz", "bz2", "xz", "iso", "dmg",
  "exe", "msi", "bin", "apk", "jar",
  "mp4", "mkv", "avi", "mov", "flv", "webm",
  "mp3", "flac", "wav", "aac", "ogg", "m4a",
  "pdf", "epub", "torrent"
]);

async function getCookies(url) {
  try {
    const cookies = await browser.cookies.getAll({ url });
    return cookies.map((c) => `${c.name}=${c.value}`).join("; ");
  } catch (e) {
    return "";
  }
}

async function sendToApp(url, referrer = "", filename = "") {
  if (!/^https?:/i.test(url)) return false;
  if (bypass.has(url)) return false;

  interceptedUrls.add(url);
  setTimeout(() => interceptedUrls.delete(url), 10000);

  const msg = {
    url,
    referrer: referrer || "",
    filename: filename || url.split("/").pop().split("?")[0] || "",
    cookie: await getCookies(url),
    userAgent: navigator.userAgent,
  };

  try {
    const res = await browser.runtime.sendNativeMessage(HOST, msg);
    if (!res || !res.ok) throw new Error((res && res.error) || "Host yanıt vermedi");
    return true;
  } catch (e) {
    console.error("ArtoDownloader host hatası, tarayıcıya dönülüyor:", e);
    bypass.add(url);
    setTimeout(() => bypass.delete(url), 30000);
    return false;
  }
}

// 1. Sağ tık menüsü
browser.contextMenus.create({
  id: "arto-download",
  title: "ArtoDownloader ile İndir",
  contexts: ["link", "video", "audio", "image"]
});

browser.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === "arto-download") {
    const targetUrl = info.linkUrl || info.srcUrl || info.pageUrl;
    if (targetUrl) {
      sendToApp(targetUrl, tab ? tab.url : "");
    }
  }
});

// 2. HTTP Yanıt Başlıklarını Yakalama (IDM stili otomatik indirme tespiti)
browser.webRequest.onHeadersReceived.addListener(
  (details) => {
    if (details.method !== "GET" && details.method !== "POST") return;
    const url = details.url;
    if (!/^https?:/i.test(url)) return;
    if (bypass.has(url) || interceptedUrls.has(url)) return;

    let isDownload = false;
    let filename = "";

    // URL uzantı kontrolü
    try {
      const pathname = new URL(url).pathname.toLowerCase();
      const ext = pathname.split(".").pop();
      if (DOWNLOAD_EXTS.has(ext)) {
        isDownload = true;
      }
    } catch (e) {}

    // Yanıt başlıkları kontrolü
    const headers = details.responseHeaders || [];
    for (const h of headers) {
      const name = h.name.toLowerCase();
      const val = (h.value || "").toLowerCase();

      if (name === "content-disposition" && (val.includes("attachment") || val.includes("filename="))) {
        isDownload = true;
        const match = /filename\*?=(?:UTF-8''|"?)([^";]+)"?/i.exec(h.value);
        if (match) filename = decodeURIComponent(match[1]);
      } else if (name === "content-type") {
        if (
          val.includes("application/octet-stream") ||
          val.includes("application/x-zip") ||
          val.includes("application/zip") ||
          val.includes("application/x-rar") ||
          val.includes("application/x-7z") ||
          val.includes("application/x-iso") ||
          val.includes("application/x-msdownload")
        ) {
          isDownload = true;
        }
      }
    }

    // İndirme ise tarayıcı akışını durdur ve ArtoDownloader'a gönder
    if (isDownload && (details.type === "main_frame" || details.type === "sub_frame")) {
      sendToApp(url, "", filename);
      return { cancel: true };
    }
  },
  { urls: ["<all_urls>"] },
  ["blocking", "responseHeaders"]
);

// 3. Tarayıcıda başlayan indirmeleri yakalama (Fallback)
browser.downloads.onCreated.addListener(async (item) => {
  const url = item.finalUrl || item.url;
  if (!/^https?:/i.test(url)) return;
  if (bypass.has(item.url) || interceptedUrls.has(url)) {
    bypass.delete(item.url);
    return;
  }

  // Tarayıcının kendi indirmesini iptal et
  try {
    await browser.downloads.cancel(item.id);
    await browser.downloads.erase({ id: item.id });
  } catch (e) {}

  const success = await sendToApp(url, item.referrer || "", item.filename);
  if (!success) {
    bypass.add(item.url);
    browser.downloads.download({ url: item.url });
  }
});

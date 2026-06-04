(() => {
  const articles = [...document.querySelectorAll("article")];
  const normalizeImage = (src) => {
    if (!src) return null;
    return src.replace(/&name=\w+/i, "&name=large");
  };

  const bookmarks = articles
    .map((node) => {
      const link = node.querySelector('a[href*="/status/"]');
      const textNode = node.querySelector('[data-testid="tweetText"]');
      const authorNode = node.querySelector('[data-testid="User-Name"]');
      const timeNode = node.querySelector("time");
      const authorParts = authorNode ? authorNode.innerText.split("\n").filter(Boolean) : [];
      const imageUrls = [...node.querySelectorAll('[data-testid="tweetPhoto"] img')]
        .map((img) => normalizeImage(img.currentSrc || img.src))
        .filter(Boolean);
      const videoElements = [...node.querySelectorAll("video")];
      const videoUrls = videoElements
        .map((video) => video.currentSrc || video.src || video.querySelector("source")?.src || null)
        .filter(Boolean);
      const videoPosterUrls = videoElements
        .map((video) => normalizeImage(video.poster || null))
        .filter(Boolean);

      return {
        url: link ? link.href : null,
        text: textNode ? textNode.innerText : "",
        author: authorParts[0] || "Unknown",
        handle: authorParts.find((part) => part.startsWith("@")) || "@unknown",
        createdAt: timeNode ? timeNode.getAttribute("datetime") : null,
        bookmarkedAt: new Date().toISOString(),
        imageUrls,
        videoUrls,
        videoPosterUrls,
      };
    })
    .filter((item) => item.url);

  const deduped = Object.values(
    bookmarks.reduce((acc, item) => {
      acc[item.url] = item;
      return acc;
    }, {})
  );

  const blob = new Blob([JSON.stringify(deduped, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `x-bookmarks-export-${new Date().toISOString().slice(0, 10)}.json`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
  console.log(`Exported ${deduped.length} bookmarks.`);
})();

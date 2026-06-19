(async () => {
  const seen = new Map();

  const normalizeImage = (src) => {
    if (!src) return null;
    return src.replace(/&name=\w+/i, "&name=large");
  };

  function extractMetric(node, testId) {
    try {
      const el = node.querySelector(`[data-testid="${testId}"]`);
      if (!el) return null;

      const text = el.innerText || "";
      const match = text.match(/[\d,.]+[KMB]?/i);

      return match ? match[0] : null;
    } catch {
      return null;
    }
  }

  function collectBookmarks() {
    const articles = document.querySelectorAll("article");

    for (const node of articles) {
      const statusLink = node.querySelector('a[href*="/status/"]');

      if (!statusLink) continue;

      const url = statusLink.href;

      const tweetId =
        url.match(/status\/(\d+)/)?.[1] || null;

      const textNode =
        node.querySelector('[data-testid="tweetText"]');

      const authorNode =
        node.querySelector('[data-testid="User-Name"]');

      const timeNode =
        node.querySelector("time");

      const authorParts = authorNode
        ? authorNode.innerText
            .split("\n")
            .filter(Boolean)
        : [];

      const imageUrls = [
        ...node.querySelectorAll(
          '[data-testid="tweetPhoto"] img'
        ),
      ]
        .map((img) =>
          normalizeImage(
            img.currentSrc || img.src
          )
        )
        .filter(Boolean);

      const videoElements = [
        ...node.querySelectorAll("video"),
      ];

      const videoPosterUrls = videoElements
        .map((video) =>
          normalizeImage(video.poster)
        )
        .filter(Boolean);

      const videoUrls = videoElements
        .map(
          (video) =>
            video.currentSrc ||
            video.src ||
            video.querySelector("source")?.src ||
            null
        )
        .filter(Boolean);

      // External links
      const externalUrls = [
        ...node.querySelectorAll("a[href]")
      ]
        .map((a) => a.href)
        .filter((href) => {
          try {
            const u = new URL(href);

            return (
              !u.hostname.includes("x.com") &&
              !u.hostname.includes("twitter.com")
            );
          } catch {
            return false;
          }
        });

      // Quoted tweets
      const quotedTweets = [
        ...node.querySelectorAll(
          'a[href*="/status/"]'
        ),
      ]
        .map((a) => a.href)
        .filter((href) => href !== url);

      const bookmark = {
        tweetId,

        url,

        text:
          textNode?.innerText || "",

        author:
          authorParts[0] || "Unknown",

        handle:
          authorParts.find((p) =>
            p.startsWith("@")
          ) || "@unknown",

        createdAt:
          timeNode?.getAttribute(
            "datetime"
          ) || null,

        bookmarkedAt:
          new Date().toISOString(),

        imageUrls: [
          ...new Set(imageUrls),
        ],

        videoUrls: [
          ...new Set(videoUrls),
        ],

        videoPosterUrls: [
          ...new Set(videoPosterUrls),
        ],

        externalUrls: [
          ...new Set(externalUrls),
        ],

        quotedTweets: [
          ...new Set(quotedTweets),
        ],

        metrics: {
          replies: extractMetric(
            node,
            "reply"
          ),

          reposts: extractMetric(
            node,
            "retweet"
          ),

          likes: extractMetric(
            node,
            "like"
          ),

          bookmarks: extractMetric(
            node,
            "bookmark"
          ),

          views: extractMetric(
            node,
            "analytics"
          ),
        },
      };

      seen.set(url, bookmark);
    }
  }

  let previousCount = 0;
  let stagnantRounds = 0;

  const MAX_STAGNANT_ROUNDS = 10;
  const SCROLL_DELAY_MS = 3000;

  console.log(
    "Starting enhanced bookmark export..."
  );

  while (
    stagnantRounds <
    MAX_STAGNANT_ROUNDS
  ) {
    collectBookmarks();

    const currentCount = seen.size;

    console.log(
      `Collected ${currentCount} bookmarks`
    );

    if (
      currentCount === previousCount
    ) {
      stagnantRounds++;
    } else {
      stagnantRounds = 0;
    }

    previousCount = currentCount;

    window.scrollTo({
      top: document.body.scrollHeight,
      behavior: "smooth",
    });

    await new Promise((resolve) =>
      setTimeout(
        resolve,
        SCROLL_DELAY_MS
      )
    );
  }

  const bookmarks = [
    ...seen.values(),
  ];

  const exportData = {
    exportedAt:
      new Date().toISOString(),

    totalBookmarks:
      bookmarks.length,

    bookmarks,
  };

  const blob = new Blob(
    [
      JSON.stringify(
        exportData,
        null,
        2
      ),
    ],
    {
      type: "application/json",
    }
  );

  const exportUrl =
    URL.createObjectURL(blob);

  const anchor =
    document.createElement("a");

  anchor.href = exportUrl;

  anchor.download =
    `x-bookmarks-export-${
      new Date()
        .toISOString()
        .slice(0, 10)
    }.json`;

  document.body.appendChild(
    anchor
  );

  anchor.click();

  anchor.remove();

  URL.revokeObjectURL(
    exportUrl
  );

  console.log(
    `Exported ${bookmarks.length} bookmarks.`
  );
})();
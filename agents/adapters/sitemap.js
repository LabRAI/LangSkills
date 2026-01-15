/* eslint-disable no-console */

function extractSitemapUrls(xmlText) {
  const xml = String(xmlText || "");
  const urls = [];
  const re = /<loc>\s*([^<\s]+)\s*<\/loc>/gi;
  for (const m of xml.matchAll(re)) urls.push(String(m[1] || "").trim());
  return urls.filter(Boolean);
}

module.exports = { extractSitemapUrls };


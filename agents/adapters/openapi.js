/* eslint-disable no-console */

function extractOpenApiCandidates(openApiJson) {
  const spec = openApiJson && typeof openApiJson === "object" ? openApiJson : null;
  if (!spec || !spec.paths || typeof spec.paths !== "object") return [];
  const out = [];
  for (const [p, ops] of Object.entries(spec.paths)) {
    if (!ops || typeof ops !== "object") continue;
    for (const [method, op] of Object.entries(ops)) {
      const m = String(method || "").toUpperCase();
      if (!/^(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)$/.test(m)) continue;
      const summary = String(op && (op.summary || op.operationId) ? op.summary || op.operationId : "").trim();
      out.push({ kind: "openapi_endpoint", method: m, path: p, title: summary || `${m} ${p}` });
    }
  }
  return out;
}

module.exports = { extractOpenApiCandidates };


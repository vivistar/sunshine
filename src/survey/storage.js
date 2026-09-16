// Client-side response store (localStorage). NOTE: with no backend, this data
// lives only in the current browser and the dashboard password is a client-side
// gate only (see AnalyzePage). Cross-device collection happens via CSV export
// from the respondent link + CSV import on the dashboard. If real shared
// collection is needed later, swap this module for API calls to a server store.

const KEY = 'sunshine.survey.responses.v1';
const TAGS_KEY = 'sunshine.survey.tags.v1'; // response_id -> [tags]

function safeRead(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

function safeWrite(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
    return true;
  } catch {
    return false;
  }
}

export function getResponses() {
  return safeRead(KEY, []);
}

export function saveResponse(response) {
  const all = getResponses();
  all.push(response);
  safeWrite(KEY, all);
  return response;
}

export function addResponses(responses) {
  const all = getResponses();
  const byId = new Map(all.map((r) => [r.response_id, r]));
  for (const r of responses) byId.set(r.response_id, r); // dedupe by id
  const merged = [...byId.values()];
  safeWrite(KEY, merged);
  return merged;
}

export function clearResponses() {
  safeWrite(KEY, []);
}

// Manual q12 tagging (PRD §5.5). Tags are stored separately keyed by response.
export function getTags() {
  return safeRead(TAGS_KEY, {});
}

export function setTagsForResponse(responseId, tags) {
  const map = getTags();
  map[responseId] = tags;
  safeWrite(TAGS_KEY, map);
  return map;
}

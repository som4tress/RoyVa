/**
 * Request classification for Home Assistant routing.
 *
 * Extracted verbatim from the ha-mcp-routing plugin so the rules can be unit
 * tested without mounting the OpenCode plugin runtime. Behaviour changes vs the
 * live version are limited to (a) entity/event history being recognised as a
 * read-only investigation instead of orchestration or person-location history,
 * and (b) media nouns no longer making a historical question "mixed".
 *
 * No household device, room, brand or prompt is named here.
 */
import {isHAConfiguration, isTechnicalRequest} from './user-scope.mjs';
import {isLocationExplanation} from './location-query.mjs';
import {isStatusReport} from './ha-reports.mjs';
import {isEntityHistory} from './history-scope.mjs';

const routingMeta = s => /\b(router|routing|openrouter)\b/.test(s) && /^(?:please )?(?:explain|describe|how|what|which|tell me|do you know|are you aware|can you explain)\b/.test(s);
const coding = s => /\b(write|implement|debug|develop|refactor|configure|install)\b.{0,45}\b(code|script|plugin|integration|server|config|automation)\b/.test(s) || /\b(read|open|inspect|review|compare|summarize)\b/.test(s) && /(?:\/[^\s]+\.[a-z0-9]+\b|\b(?:files?|documents?|source code)\b)/.test(s);
const PEOPLE = /\b(shobha|shubha|somdutta|shivangsh|shivi|pecky)\b/;
const history = s => {
  if (/\b(stock|news|flight|ticket|vacation|holiday)\b/.test(s)) return false;
  if (/\b(visit\w*|locations?|where)\b/.test(s) && /\b(today|yesterday|visited|history|locations|been|went)\b/.test(s)) return true;
  return false;
};
const presence = s => PEOPLE.test(s) && !/\b(turn|switch|set|dim|lights?|fans?|thermostat)\b/.test(s) && /\b(where\s+(?:is|are)|where'?s|current location|location|locate|home|away|zone)\b/.test(s) && !/\b(yesterday|visited|visits|history|been|went|earlier|past|locations)\b/.test(s);

// Explicit physical controls may name an area or alias instead of a device noun.
export const isHAControl = text => {
  const s = text.trim().toLowerCase().replace(/[.!?]+$/, '');
  if (/\b(server|service|process|computer|linux|windows|opencode|vllm|thinking|reasoning|notifications?|subscription|account|logging|debug|vpn|firewall)\b/.test(s)) return false;
  return /^(?:please\s+)?(?:turn|switch)\s+(?:on|off)\s+(?!it$|them$|those$|both$|all of them$).+/.test(s)
    || /^(?:please\s+)?(?:turn|switch)\s+(?!it |them |those |both ).+\s+(?:on|off)$/.test(s);
};
const devices = s => /\b(light\w*|dimmer\w*|fan\w*|thermostat|curtain\w*|blind\w*|switches?|devices?|entities|lamps?)\b/.test(s) && /\b(on|off|state|status|dim|bright\w*|set|turn|switch|are|is)\b/.test(s);

export function isMixedRequest(text) {
  const s = text.toLowerCase();
  if (coding(s) || routingMeta(s)) return false;
  const clauses = s.split(/\s+(?:and|then|also)\s+(?=(?:turn|switch|set|run|show|share|summarize|analy[sz]e|provide|list|check)\b)/);
  if (clauses.length > 1 && clauses.every(isHAControl)) return false;
  if (clauses.length > 1 && isHAControl(clauses[0])) return true;
  // Only media delivery/retrieval is a mixed task. Mentioning a camera, doorbell or
  // recording inside a historical question is a read-only investigation, not
  // orchestration. Treating the noun as "mixed" sent history questions through
  // delegation that had no retrieval tool and produced false "no tool" answers.
  const mediaAction = /\b(send|share|play|download|open|attach|show me the (?:video|clip|footage)|analy[sz]e (?:this|the) (?:video|clip|footage))\b/.test(s) && /\b(video|footage|clip|recording|camera)\b/.test(s);
  return (devices(s) && /\b(?:and|then|also)\s+(?:then\s+)?(?:turn|switch|set|run|show|share|analy[sz]e|provide|list|check)\b/.test(s))
    || (history(s) && devices(s))
    || mediaAction;
}

export function classify(text) {
  const s = text.toLowerCase();
  if (isTechnicalRequest(s) || isHAConfiguration(s) || coding(s) || routingMeta(s) || isLocationExplanation(s) || isMixedRequest(s)) return null;
  // Device/event/recording history is its own read-only investigation class. Returning
  // it explicitly stops learned phrases and semantic labels from narrowing it to the
  // person zone-history tool.
  if (isEntityHistory(s)) return 'investigation';
  if (presence(s)) return 'devices';
  if (history(s)) return 'history';
  if (isStatusReport(text)) return 'devices';
  if (/\b(rooms?|bedrooms?|areas?|floors?)\b/.test(s) && /\b(status|states?|what is|how is|check|show)\b/.test(s) && !/\b(news|stock|hotel|booking|ticket|history|yesterday|why|explain)\b/.test(s)) return 'devices';
  if (/\b(home assistant|homeassistant|ha mcp)\b/.test(s) || devices(s) || isHAControl(s)) return 'devices';
  return null;
}

export {coding, routingMeta};

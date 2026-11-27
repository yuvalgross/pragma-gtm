// HubSpot deal -> analytics.deals row. Same columns as demo_deals so every query keeps working.
const GO_LIVE = '2025-11-01'; // the month the signal engine went live
const SOURCES = { REFERRAL: 'Referral', SIGNAL: 'Signal-led', INBOUND: 'Inbound', GENERIC: 'Generic outbound' };
const rows = [];
for (const item of $input.all()) {
  const p = item.json.properties || item.json;
  const stage = (p.dealstage || '').toLowerCase();
  const isWon = stage === 'closedwon';
  const isClosed = isWon || stage === 'closedlost';
  const created = new Date(p.createdate), closed = p.closedate ? new Date(p.closedate) : null;
  const src = SOURCES[(p.lead_source || '').toUpperCase()] || 'Generic outbound';
  rows.push({
    hubspot_id: String(item.json.dealId || item.json.id),
    lead_source: src,
    is_closed: isClosed,
    is_won: isWon,
    amount_eur: Number(p.amount || 0),
    days_to_close: isClosed && closed ? Math.round((closed - created) / 86400000) : null,
    period: (closed || created).toISOString().slice(0, 10) < GO_LIVE ? 'Before signals' : 'After signals',
    synced_at: new Date().toISOString()
  });
}
return [{ json: { rows, count: rows.length } }];
"""Fixed, read-only capture scripts shared by both Playwright APIs."""
IDENTITY = "() => ({url: location.href, document: String(performance.timeOrigin)})"
FIRST_TEXT = """(elements, limit) => {
 const text = elements.length ? elements[0].innerText : '';
 if (typeof text !== 'string') throw Error('innerText is unavailable');
 return {text: text.slice(0, limit), truncated: text.length > limit};
}"""
# Playwright evaluates :visible, preserving its selector semantics. Capture all
# visible reaction facts, then let Core bind them to backend-resolved messages.
REACTION_SELECTOR = ('.messages-list__scroller [data-message-id]:visible '
                     '.reactions-wrapper .reaction-button--trigger:visible .reaction-emoji:visible')
REACTIONS = """(elements, limits) => ({
 truncated: elements.length > limits.records,
 records: elements.slice(0, limits.records).map(el => {
   const text = el.innerText;
   if (text.length > limits.text) throw Error('reaction text exceeds allowance');
   return {message_id: el.closest('[data-message-id]').getAttribute('data-message-id'),
           text, selected: el.closest('.reaction-button--trigger').classList.contains('button-vue--primary')};
 })
})"""

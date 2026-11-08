# Layout Components

Use these simple HTML components where they help the reader. The publishing step styles them for you. Use only these class names. Do not add inline styles, scripts or images, and do not add a table of contents (one is generated).

- **Quick answer** (use once, after the first paragraph): `<div class="quick-answer"><p>Two or three sentences that answer the main question.</p></div>`
- **Tip** (at most 3): `<div class="tip"><p>One practical tip.</p></div>`
- **Heads up** (at most 2), for a real limit, cost, risk or thing to double-check: `<div class="warning"><p>What to watch out for.</p></div>`
- **Steps**, for how-to tasks: `<ol class="steps"><li><strong>Do this.</strong> Short explanation.</li></ol>`
- **Comparison table**, only when comparing three or more options across at least three points: `<table class="compare"><thead><tr><th>Option</th><th>Best for</th><th>Free plan</th></tr></thead><tbody><tr><td>Name</td><td>Who it suits</td><td>What is free</td></tr></tbody></table>`. Keep each cell under 12 words. Every fact in the table must come from the research brief.

Everything else stays plain: short paragraphs, `<h2>` and `<h3>` headings, and normal lists.

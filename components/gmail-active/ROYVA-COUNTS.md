# Gmail count metadata

listMessages and searchMessages return returned_count (exact messages.length for this page), has_more (whether nextPageToken exists), total_estimate (Gmail resultSizeEstimate, or null when absent), plus existing messages/nextPageToken fields. The estimate is approximate and is not an exact or cumulative total. Zero-result suggestions retain these fields.

Counts precede message arrays in the serialized result. No automatic pagination was added. Tool descriptions instruct the model to use these fields and ask before fetching additional pages. This removes counting work from the model; it does not force the model to quote the fields correctly.

Tests: npm run build, then node --experimental-test-module-mocks --test tests/counts.test.mjs. Five mocked cases cover differing estimate/page count, pagination without automatic fetching, explicit next-page requests, zero results with suggestions, and omitted message arrays. They make no Gmail account calls.

# Privacy

Dify Extractor processes the file supplied to the tool in the plugin runtime. It does not collect
analytics, create user profiles, or retain extracted document content itself.

When a Markdown or DOCX file references an external image, the plugin may request that HTTP(S) URL
and upload the returned image to the Dify file service so it can be included in the tool output.
This discloses the plugin runtime's network address and normal HTTP request metadata to the host of
the referenced image. Embedded images are uploaded only to the configured Dify file service.

Operational logs may contain source filenames, image URLs, and error descriptions. Retention and
access to files and logs are controlled by the operator of the Dify deployment and the referenced
image hosts.

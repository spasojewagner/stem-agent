export function CodeBlock({ code, label }: { code: string; label?: string }) {
  return (
    <figure className="overflow-hidden rounded-md border border-line bg-code">
      {label && <figcaption className="border-b border-line px-3 py-1.5 font-mono text-xs text-muted">{label}</figcaption>}
      <pre className="max-h-[32rem] overflow-auto px-3 py-2.5 font-mono text-[12.5px] leading-relaxed">
        <code>{code}</code>
      </pre>
    </figure>
  );
}

/** A unified diff, one file after another, with added and removed lines coloured. */
export function DiffView({ diff }: { diff: string }) {
  if (!diff.trim()) return <p className="text-sm text-muted">This change has no file differences.</p>;
  const files = diff.split(/^(?=diff --git )/m).filter(Boolean);
  return (
    <div className="space-y-4">
      {files.map((block, i) => {
        const [header, ...rest] = block.split("\n");
        const path = header.replace(/^diff --git a\/(\S+) b\/.*$/, "$1");
        const body = rest.filter((l) => !/^(index |--- |\+\+\+ |new file mode|deleted file mode)/.test(l));
        while (body.length && body[body.length - 1] === "") body.pop();
        return (
          <figure key={i} className="overflow-hidden rounded-md border border-line bg-code">
            <figcaption className="border-b border-line px-3 py-1.5 font-mono text-xs">{path}</figcaption>
            <pre className="max-h-[28rem] overflow-auto py-1.5 font-mono text-[12.5px] leading-relaxed">
              {body.map((line, j) => {
                const tone = line.startsWith("+") ? "bg-hema-soft text-ink"
                  : line.startsWith("-") ? "bg-eosin-soft text-ink"
                    : line.startsWith("@@") ? "text-muted" : "";
                return <div key={j} className={`px-3 whitespace-pre ${tone}`}>{line || " "}</div>;
              })}
            </pre>
          </figure>
        );
      })}
    </div>
  );
}

import { Document, Page, pdfjs } from "react-pdf";
import { useEffect, useMemo, useState } from "react";

pdfjs.GlobalWorkerOptions.workerSrc = `//cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjs.version}/pdf.worker.min.js`;

type Props = {
  fileUrl: string | null;
  highlightTerms?: string[];
};

export default function PdfViewer({ fileUrl, highlightTerms = [] }: Props) {
  const [numPages, setNumPages] = useState<number | null>(null);

  // Build a quick regex for highlights (basic text-layer highlighting is limited)
  const highlightRegex = useMemo(() => {
    const terms = highlightTerms
      .filter(Boolean)
      .map((t) => t.trim())
      .filter((t) => t.length > 2)
      .slice(0, 20);
    if (terms.length === 0) return null;
    return new RegExp(`(${terms.map((t) => escapeRegExp(t)).join("|")})`, "gi");
  }, [highlightTerms]);

  useEffect(() => () => setNumPages(null), [fileUrl]);

  if (!fileUrl) return <div className="p-4 text-sm text-gray-500">No file selected.</div>;

  return (
    <div className="w-full overflow-x-auto">
      <Document file={fileUrl} onLoadSuccess={(info) => setNumPages(info.numPages)}>
        {Array.from(new Array(numPages || 0), (_el, index) => (
          <div key={`pg_${index + 1}`} className="border-b">
<Page
  pageNumber={index + 1}
  width={800}
/>          </div>
        ))}
      </Document>
    </div>
  );
}

function escapeRegExp(s: string) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function renderWithHighlights(regex: RegExp) {
  return ({ str }: { str: string }) => {
    const parts = str.split(regex);
    if (parts.length === 1) return str;
    return (
      <>
        {parts.map((p, i) =>
          regex.test(p) ? (
            <mark key={i} className="bg-yellow-200">
              {p}
            </mark>
          ) : (
            <span key={i}>{p}</span>
          )
        )}
      </>
    );
  };
}


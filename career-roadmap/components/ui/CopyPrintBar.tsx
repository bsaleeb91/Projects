"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";

export function CopyPrintBar({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="no-print flex gap-3">
      <Button variant="secondary" onClick={handleCopy}>
        {copied ? "Copied" : "Copy"}
      </Button>
      <Button variant="secondary" onClick={() => window.print()}>
        Print
      </Button>
    </div>
  );
}

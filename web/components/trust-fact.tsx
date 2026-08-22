import type { ReactNode } from "react";


interface TrustFactProps {
  label: string;
  children: ReactNode;
}

export default function TrustFact({ label, children }: TrustFactProps) {
  return (
    <div className="trust-fact">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

import { CardHeader } from "@/components/card-header";
import { SiteFooter } from "@/components/site-footer";
import { SkipLink } from "@/components/skip-link";

export default function CardLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <SkipLink />
      <CardHeader />
      {/* The footer starts below the first screen: a card that grows late never moves it in view. */}
      <div className="min-h-dvh">{children}</div>
      <SiteFooter />
    </>
  );
}

import { Header } from "@/lib/ui/Header";
import { NavBar } from "@/lib/ui/NavBar";
import type { ReactNode } from "react";

export default function AuthenticatedLayout({
  children,
}: {
  children: ReactNode;
}): JSX.Element {
  return (
    <>
      <Header />
      <main className="mx-auto max-w-lg px-4 pb-20 pt-4">{children}</main>
      <NavBar />
    </>
  );
}

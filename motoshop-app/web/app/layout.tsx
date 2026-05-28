import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "MotoShop",
  description: "PWA de consulta remota para MotoShop",
};

export default function RootLayout({
  children,
}: {
  children: ReactNode;
}): JSX.Element {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  );
}

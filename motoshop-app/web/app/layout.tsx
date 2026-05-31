import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import { ToastProvider } from "@/lib/ui/Toast";
import "./globals.css";

export const metadata: Metadata = {
  title: "MotoShop",
  description: "Consulta remota de catálogo, stock y ventas",
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: "MotoShop",
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
  themeColor: "#C83828",
};

export default function RootLayout({
  children,
}: {
  children: ReactNode;
}): JSX.Element {
  return (
    <html lang="es">
      <body className="min-h-screen bg-background text-text-primary antialiased">
        <ToastProvider>{children}</ToastProvider>
      </body>
    </html>
  );
}

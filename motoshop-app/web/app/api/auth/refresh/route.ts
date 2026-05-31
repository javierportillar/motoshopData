import { NextRequest, NextResponse } from "next/server";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "https://motoshop-cloud-api.onrender.com";

export async function POST(req: NextRequest) {
  const refreshToken = req.cookies.get("motoshop_refresh")?.value;

  if (!refreshToken) {
    return NextResponse.json({ detail: "No refresh token" }, { status: 401 });
  }

  try {
    const resp = await fetch(`${API_BASE}/api/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: refreshToken }),
    });

    if (!resp.ok) {
      return NextResponse.json({ detail: "Refresh inválido" }, { status: 401 });
    }

    const data = await resp.json();
    const { access_token, refresh_token: newRefresh } = data;

    const res = NextResponse.json({ message: "Token refrescado" });

    res.cookies.set("motoshop_token", access_token, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      path: "/",
      maxAge: 15 * 60,
    });

    if (newRefresh) {
      res.cookies.set("motoshop_refresh", newRefresh, {
        httpOnly: true,
        secure: process.env.NODE_ENV === "production",
        sameSite: "lax",
        path: "/",
        maxAge: 7 * 24 * 60 * 60,
      });
    }

    return res;
  } catch {
    return NextResponse.json(
      { detail: "No se pudo conectar con el servidor" },
      { status: 502 },
    );
  }
}

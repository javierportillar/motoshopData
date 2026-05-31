import { NextRequest, NextResponse } from "next/server";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "https://api.fragloesja.uk";

export async function POST(req: NextRequest) {
  const body = await req.json();
  const { username, password } = body;

  if (!username || !password) {
    return NextResponse.json(
      { detail: "Usuario y contraseña requeridos" },
      { status: 400 },
    );
  }

  try {
    const resp = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });

    if (!resp.ok) {
      const error = await resp.json().catch(() => ({ detail: "Credenciales inválidas" }));
      return NextResponse.json(error, { status: resp.status });
    }

    const data = await resp.json();
    const { access_token, refresh_token } = data;

    const res = NextResponse.json({
      user: username,
      message: "Login exitoso",
      access_token,
    });

    res.cookies.set("motoshop_token", access_token, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      path: "/",
      maxAge: 15 * 60, // 15 min
    });

    if (refresh_token) {
      res.cookies.set("motoshop_refresh", refresh_token, {
        httpOnly: true,
        secure: process.env.NODE_ENV === "production",
        sameSite: "lax",
        path: "/",
        maxAge: 7 * 24 * 60 * 60, // 7 days
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

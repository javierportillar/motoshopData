import { NextRequest, NextResponse } from "next/server";

export async function GET(req: NextRequest) {
  const token = req.cookies.get("motoshop_token")?.value;

  if (!token) {
    return NextResponse.json({ detail: "No autenticado" }, { status: 401 });
  }

  try {
    const parts = token.split(".");
    const b64 = parts[1] ?? "";
    const payload = JSON.parse(Buffer.from(b64, "base64").toString("utf-8"));
    const role = payload.rol ?? payload.role ?? "";
    const user = payload.sub ?? payload.username ?? payload.user ?? "unknown";

    if (role !== "admin") {
      return NextResponse.json(
        { detail: "Se requiere rol admin", user, role },
        { status: 403 },
      );
    }

    return NextResponse.json({
      message: "Admin ping ok",
      user,
      role,
    });
  } catch {
    return NextResponse.json({ detail: "Token inválido" }, { status: 401 });
  }
}

import { NextResponse } from "next/server";

import { getSupabaseAuthServerClient } from "@/lib/supabase/auth-server";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const code = url.searchParams.get("code");

  if (!code) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("error", "link_non_valido_o_scaduto");
    return NextResponse.redirect(loginUrl);
  }

  const supabase = await getSupabaseAuthServerClient();
  const { error } = await supabase.auth.exchangeCodeForSession(code);

  if (error) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("error", "link_non_valido_o_scaduto");
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.redirect(new URL("/dashboard", request.url));
}

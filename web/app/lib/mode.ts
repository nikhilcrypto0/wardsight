// "public" = the hosted demo: only the ward replay (a static file), no Python API,
// so a visitor can never trigger an API call or change data.
export const IS_PUBLIC = process.env.NEXT_PUBLIC_WARDSIGHT_MODE === "public";

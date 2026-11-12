export type UiLanguage = "en" | "ko" | "ja";

export const UI_LANGUAGE_KEY = "ui:language";

export function getSavedLanguage(): UiLanguage {
  if (typeof window === "undefined") return "en";
  const value = window.localStorage.getItem(UI_LANGUAGE_KEY);
  if (value === "ko" || value === "ja" || value === "en") return value;
  return "en";
}

export function applyLanguage(language: UiLanguage) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(UI_LANGUAGE_KEY, language);
  window.dispatchEvent(new CustomEvent("ui-language:changed", { detail: language }));
}

export const TRANSLATIONS = {
  en: {
    search: "Search",
    settings: "Settings",
    new_page: "New page",
    new_database: "New database",
    inline_database: "Inline database",
    favorites: "Favorites",
    pages: "Pages",
    trash: "Trash",
    no_favorites: "No favorite pages",
    no_trash: "No pages in trash",
    workspace: "Workspace",
    private: "private",
    invite_members: "Invite members",
    send_invite: "Send invite",
    add_account: "Add another account",
    templates: "Templates",
    profile: "Profile",
    logout: "Log out all accounts",
    people_with_access: "People with access",
    public_pages: "Public pages",
    preferences: "Preferences",
    notifications: "Notifications",
    general: "General",
    people: "People",
    emoji: "Emoji",
  },
  ko: {
    search: "검색",
    settings: "설정",
    new_page: "새 페이지",
    new_database: "새 데이터베이스",
    inline_database: "인라인 데이터베이스",
    favorites: "즐겨찾기",
    pages: "페이지",
    trash: "휴지통",
    no_favorites: "즐겨찾기 페이지가 없습니다",
    no_trash: "휴지통이 비어 있습니다",
    workspace: "워크스페이스",
    private: "비공개",
    invite_members: "멤버 초대",
    send_invite: "초대 보내기",
    add_account: "계정 추가",
    templates: "템플릿",
    profile: "프로필",
    logout: "모든 계정 로그아웃",
    people_with_access: "접근 가능한 멤버",
    public_pages: "공개 페이지",
    preferences: "환경설정",
    notifications: "알림",
    general: "일반",
    people: "사람",
    emoji: "이모지",
  },
  ja: {
    search: "検索",
    settings: "設定",
    new_page: "新規ページ",
    new_database: "新規データベース",
    inline_database: "インラインデータベース",
    favorites: "お気に入り",
    pages: "ページ",
    trash: "ゴミ箱",
    no_favorites: "お気に入りのページがありません",
    no_trash: "ゴミ箱は空です",
    workspace: "ワークスペース",
    private: "非公開",
    invite_members: "メンバーを招待",
    send_invite: "招待を送信",
    add_account: "アカウント追加",
    templates: "テンプレート",
    profile: "プロフィール",
    logout: "すべてのアカウントからログアウト",
    people_with_access: "アクセス可能なメンバー",
    public_pages: "公開ページ",
    preferences: "環境設定",
    notifications: "通知",
    general: "一般",
    people: "メンバー",
    emoji: "絵文字",
  },
} as const;

type TranslationKey = keyof typeof TRANSLATIONS.en;

export function t(language: UiLanguage, key: TranslationKey): string {
  return TRANSLATIONS[language][key] ?? TRANSLATIONS.en[key] ?? key;
}

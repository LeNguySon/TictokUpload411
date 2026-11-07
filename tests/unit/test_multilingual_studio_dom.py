"""Unit tests for Multilingual TikTok Studio DOM Automation (TDD).

Validates that Spanish, English, Korean, Japanese, and Vietnamese strings
are correctly recognized across:
1. Joyride Onboarding dismissal
2. Post button detection
3. Privacy level selection
4. Interaction permissions (Comment, Duet, Stitch)
5. Publication confirmation detection
"""


class MultilingualDomMatcher:
    """Helper mimicking the in-browser JavaScript matching logic in sammonny TikTok SDK."""

    JOYRIDE_KEYWORDS = [
        "ok", "got it", "skip", "dismiss", "next", "close",
        "đồng ý", "đã hiểu", "bỏ qua", "tiếp tục", "đóng",
        "了解", "次へ", "スキップ", "閉じる",
        "aceptar", "entendido", "omitir", "saltar", "siguiente", "cerrar",
        "확인", "알겠습니다", "건너뛰기", "다음", "닫기",
    ]

    POST_KEYWORDS = [
        "post", "schedule",
        "đăng", "lên lịch",
        "投稿", "スケジュール",
        "publicar", "programar",
        "게시", "게시하기", "예약",
    ]

    PRIVACY_SELECTORS = {
        "self": [
            "only you", "private", "only me",
            "chỉ mình tôi", "riêng tư",
            "自分のみ", "非公開",
            "solo tú", "solo tu", "privado", "solo yo",
            "나만 보기", "비공개",
        ],
        "friends": [
            "friends", "mutuals", "followers",
            "bạn bè", "người theo dõi",
            "友達", "相互フォロワー",
            "amigos", "seguidores",
            "친구", "맞팔로우",
        ],
        "public": [
            "public", "everyone",
            "công khai", "mọi người",
            "誰でも", "公開",
            "público", "publico", "todos", "cualquiera",
            "모든 사람", "전체 공개", "공개",
        ],
    }

    PERMISSION_KEYWORDS = {
        "comment": [
            "comment", "comments",
            "bình luận",
            "コメント",
            "comentario", "comentarios",
            "댓글",
        ],
        "duet": [
            "duet",
            "デュエット",
            "dúo", "duo",
            "듀엣",
        ],
        "stitch": [
            "stitch",
            "ステッチ",
            "pegar",
            "이어붙이기", "스티치",
        ],
    }

    CONFIRMATION_KEYWORDS = [
        # English
        "uploaded", "manage your posts", "your video has been", "post now", "view post",
        # Vietnamese
        "đã tải lên", "quản lý bài viết", "video của bạn đã được", "xem bài viết",
        # Japanese
        "投稿しました", "動画を管理", "アップロード完了", "アップロードしました", "コンテンツを管理",
        # Spanish
        "se ha subido", "gestionar tus publicaciones", "tu video se ha", "tu vídeo se ha", "ver publicación", "publicado", "subida completada", "gestionar publicaciones",
        # Korean
        "업로드됨", "게시물 관리", "동영상이 업로드되었습니다", "게시됨", "게시물 보기", "업로드 완료",
    ]

    @classmethod
    def matches_joyride_dismiss(cls, button_text: str) -> bool:
        t = button_text.strip().lower()
        return any(k.lower() == t for k in cls.JOYRIDE_KEYWORDS)

    @classmethod
    def matches_post_button(cls, button_text: str) -> bool:
        t = button_text.strip().lower()
        return any(k.lower() in t for k in cls.POST_KEYWORDS)

    @classmethod
    def matches_privacy(cls, label_text: str, target_category: str) -> bool:
        t = label_text.strip().lower()
        candidates = cls.PRIVACY_SELECTORS.get(target_category, [])
        return any(c.lower() in t for c in candidates)

    @classmethod
    def matches_permission(cls, container_text: str, perm_type: str) -> bool:
        t = container_text.strip().lower()
        candidates = cls.PERMISSION_KEYWORDS.get(perm_type, [])
        return any(c.lower() in t for c in candidates)

    @classmethod
    def matches_confirmation(cls, page_text: str) -> bool:
        t = page_text.strip().lower()
        return any(k.lower() in t for k in cls.CONFIRMATION_KEYWORDS)


def test_joyride_onboarding_dismissal_all_languages():
    # Spanish
    assert MultilingualDomMatcher.matches_joyride_dismiss("Aceptar")
    assert MultilingualDomMatcher.matches_joyride_dismiss("Entendido")
    assert MultilingualDomMatcher.matches_joyride_dismiss("Omitir")
    assert MultilingualDomMatcher.matches_joyride_dismiss("Saltar")
    assert MultilingualDomMatcher.matches_joyride_dismiss("Cerrar")
    # Korean
    assert MultilingualDomMatcher.matches_joyride_dismiss("확인")
    assert MultilingualDomMatcher.matches_joyride_dismiss("알겠습니다")
    assert MultilingualDomMatcher.matches_joyride_dismiss("건너뛰기")
    assert MultilingualDomMatcher.matches_joyride_dismiss("닫기")
    # English
    assert MultilingualDomMatcher.matches_joyride_dismiss("OK")
    assert MultilingualDomMatcher.matches_joyride_dismiss("Got it")
    assert MultilingualDomMatcher.matches_joyride_dismiss("Skip")
    # Japanese
    assert MultilingualDomMatcher.matches_joyride_dismiss("了解")
    assert MultilingualDomMatcher.matches_joyride_dismiss("スキップ")
    # Vietnamese
    assert MultilingualDomMatcher.matches_joyride_dismiss("Đồng ý")
    assert MultilingualDomMatcher.matches_joyride_dismiss("Bỏ qua")


def test_post_button_detection_all_languages():
    # Spanish
    assert MultilingualDomMatcher.matches_post_button("Publicar")
    assert MultilingualDomMatcher.matches_post_button("Programar")
    # Korean
    assert MultilingualDomMatcher.matches_post_button("게시")
    assert MultilingualDomMatcher.matches_post_button("게시하기")
    assert MultilingualDomMatcher.matches_post_button("예약")
    # Japanese
    assert MultilingualDomMatcher.matches_post_button("投稿")
    assert MultilingualDomMatcher.matches_post_button("スケジュール")
    # English
    assert MultilingualDomMatcher.matches_post_button("Post")
    assert MultilingualDomMatcher.matches_post_button("Schedule")
    # Vietnamese
    assert MultilingualDomMatcher.matches_post_button("Đăng")
    assert MultilingualDomMatcher.matches_post_button("Lên lịch")


def test_privacy_selection_all_languages():
    # Public
    assert MultilingualDomMatcher.matches_privacy("Público", "public")
    assert MultilingualDomMatcher.matches_privacy("Todos", "public")
    assert MultilingualDomMatcher.matches_privacy("모든 사람", "public")
    assert MultilingualDomMatcher.matches_privacy("전체 공개", "public")
    assert MultilingualDomMatcher.matches_privacy("誰でも", "public")
    assert MultilingualDomMatcher.matches_privacy("Công khai", "public")
    assert MultilingualDomMatcher.matches_privacy("Everyone", "public")

    # Friends
    assert MultilingualDomMatcher.matches_privacy("Amigos", "friends")
    assert MultilingualDomMatcher.matches_privacy("친구", "friends")
    assert MultilingualDomMatcher.matches_privacy("友達", "friends")
    assert MultilingualDomMatcher.matches_privacy("Bạn bè", "friends")
    assert MultilingualDomMatcher.matches_privacy("Friends", "friends")

    # Self Only / Private
    assert MultilingualDomMatcher.matches_privacy("Solo tú", "self")
    assert MultilingualDomMatcher.matches_privacy("Privado", "self")
    assert MultilingualDomMatcher.matches_privacy("나만 보기", "self")
    assert MultilingualDomMatcher.matches_privacy("비공개", "self")
    assert MultilingualDomMatcher.matches_privacy("自分のみ", "self")
    assert MultilingualDomMatcher.matches_privacy("Chỉ mình tôi", "self")
    assert MultilingualDomMatcher.matches_privacy("Only you", "self")


def test_permissions_interaction_all_languages():
    # Comment
    assert MultilingualDomMatcher.matches_permission("Permitir comentarios", "comment")
    assert MultilingualDomMatcher.matches_permission("댓글 허용", "comment")
    assert MultilingualDomMatcher.matches_permission("コメントを許可", "comment")
    assert MultilingualDomMatcher.matches_permission("Cho phép bình luận", "comment")
    assert MultilingualDomMatcher.matches_permission("Allow comments", "comment")

    # Duet
    assert MultilingualDomMatcher.matches_permission("Permitir Dúo", "duet")
    assert MultilingualDomMatcher.matches_permission("듀엣 허용", "duet")
    assert MultilingualDomMatcher.matches_permission("デュエットを許可", "duet")
    assert MultilingualDomMatcher.matches_permission("Cho phép Duet", "duet")
    assert MultilingualDomMatcher.matches_permission("Allow Duet", "duet")

    # Stitch
    assert MultilingualDomMatcher.matches_permission("Permitir Pegar", "stitch")
    assert MultilingualDomMatcher.matches_permission("이어붙이기 허용", "stitch")
    assert MultilingualDomMatcher.matches_permission("ステッチを許可", "stitch")
    assert MultilingualDomMatcher.matches_permission("Cho phép Stitch", "stitch")
    assert MultilingualDomMatcher.matches_permission("Allow Stitch", "stitch")


def test_publication_confirmation_all_languages():
    # Spanish
    assert MultilingualDomMatcher.matches_confirmation("Tu video se ha subido a TikTok")
    assert MultilingualDomMatcher.matches_confirmation("Gestionar tus publicaciones")
    assert MultilingualDomMatcher.matches_confirmation("Subida completada con éxito")
    # Korean
    assert MultilingualDomMatcher.matches_confirmation("동영상이 업로드되었습니다")
    assert MultilingualDomMatcher.matches_confirmation("게시물 관리")
    assert MultilingualDomMatcher.matches_confirmation("동영상 업로드 완료")
    # Japanese
    assert MultilingualDomMatcher.matches_confirmation("動画を投稿しました")
    assert MultilingualDomMatcher.matches_confirmation("動画を管理")
    assert MultilingualDomMatcher.matches_confirmation("アップロード完了")
    # English
    assert MultilingualDomMatcher.matches_confirmation("Your video has been uploaded")
    assert MultilingualDomMatcher.matches_confirmation("Manage your posts")
    # Vietnamese
    assert MultilingualDomMatcher.matches_confirmation("Video của bạn đã được tải lên")
    assert MultilingualDomMatcher.matches_confirmation("Quản lý bài viết của bạn")

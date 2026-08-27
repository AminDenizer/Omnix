import json
import hmac
import hashlib
import datetime
from typing import Dict, Any, Tuple, Optional
from database import Database


# Secret cryptographic salt for signing backup files
BACKUP_SECRET_SALT = "OMNIX_SECURE_HMAC_SALT_2026_@AGY_BASE_EDITION"
LEGACY_BACKUP_SECRET_SALT = "ELECSTORE_SECURE_HMAC_SALT_2026_@AGY_BASE_EDITION"
BACKUP_MAGIC_HEADER = "OMNIX_SECURE_BACKUP"
LEGACY_MAGIC_HEADER = "ELECSTORE_SECURE_BACKUP"
BACKUP_VERSION = "1.0"


class BackupManager:
    """Dedicated module for creating and restoring digitally-signed backup files with integrity validation."""

    @staticmethod
    def _compute_signature(payload_str: str, salt: str = BACKUP_SECRET_SALT) -> str:
        """Compute HMAC-SHA256 digital signature from the data payload string."""
        return hmac.new(
            salt.encode('utf-8'),
            payload_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    @classmethod
    def create_backup(cls, db: Database, target_file_path: str, is_advanced: bool = False) -> Tuple[bool, str]:
        """
        Create a digitally-signed backup file:
        - Standard mode: components and stock history
        - Advanced mode: components, stock history, custom categories, custom packages, and settings
        """
        try:
            comps = db.get_all_components()
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 1. Extract component data
            components_data = []
            for c in comps:
                components_data.append({
                    "id": c.id,
                    "name": c.name,
                    "value": c.value,
                    "package": c.package,
                    "category": c.category,
                    "quantity": c.quantity,
                    "min_alert": c.min_alert,
                    "drawers": c.drawers,
                    "description": c.description,
                    "created_at": c.created_at,
                    "updated_at": c.updated_at
                })

            # 2. Extract transaction history
            stock_history_data = []
            with db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM stock_history ORDER BY id ASC")
                for r in cursor.fetchall():
                    stock_history_data.append(dict(r))

            payload: Dict[str, Any] = {
                "components": components_data,
                "stock_history": stock_history_data
            }

            # 3. Extract advanced configuration data if selected
            if is_advanced:
                payload["custom_categories"] = db.get_custom_categories()
                payload["custom_packages"] = db.get_custom_packages()
                payload["category_mode"] = db.get_category_mode()
                payload["package_mode"] = db.get_package_mode()

            payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
            signature = cls._compute_signature(payload_json)

            backup_doc = {
                "magic": BACKUP_MAGIC_HEADER,
                "version": BACKUP_VERSION,
                "backup_type": "ADVANCED" if is_advanced else "STANDARD",
                "created_at": now_str,
                "total_components": len(components_data),
                "signature": signature,
                "payload": payload
            }

            with open(target_file_path, "w", encoding="utf-8") as f:
                json.dump(backup_doc, f, ensure_ascii=False, indent=2)

            type_title = "پیشرفته (شامل دسته‌ها و پکیج‌ها)" if is_advanced else "عادی"
            msg = f"فایل پشتیبان {type_title} با موفقیت در مسیر ذخیره شد.\nتعداد قطعات: {len(components_data)}"
            print(f"[INFO] [BACKUP] Created {backup_doc['backup_type']} backup at {target_file_path}")
            return True, msg

        except Exception as e:
            err_msg = f"خطا در ایجاد فایل پشتیبان: {str(e)}"
            print(f"[ERROR] [BACKUP] Failed to create backup: {e}")
            return False, err_msg

    @classmethod
    def verify_backup_file(cls, file_path: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Verify the cryptographic signature and structural integrity of a backup file.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                doc = json.load(f)

            if not isinstance(doc, dict):
                return False, "ساختار فایل پشتیبان نامعتبر است (فرمت غیراستاندارد).", None

            # Verify magic identification header (supports both Omnix and legacy formats)
            magic = doc.get("magic")
            if magic not in (BACKUP_MAGIC_HEADER, LEGACY_MAGIC_HEADER):
                return False, "این فایل یک فایل پشتیبان رسمی از سامانه Omnix نیست و فاقد شناسه اختصاصی برنامه می‌باشد.", None

            stored_sig = doc.get("signature")
            payload = doc.get("payload")

            if not stored_sig or not payload or not isinstance(payload, dict):
                return False, "امضای دیجیتال یا بخش داده‌های فایل مفقود یا مخدوش شده است.", None

            # Compute and verify cryptographic HMAC signature
            payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
            calculated_sig = cls._compute_signature(payload_json, BACKUP_SECRET_SALT)
            
            # If current salt doesn't match, check legacy salt for backward compatibility
            if not hmac.compare_digest(stored_sig, calculated_sig):
                legacy_sig = cls._compute_signature(payload_json, LEGACY_BACKUP_SECRET_SALT)
                if not hmac.compare_digest(stored_sig, legacy_sig):
                    return False, "خطای اعتبارسنجی امنیتی: امضای دیجیتال فایل همخوانی ندارد. این فایل احتمالاً دستکاری شده یا نامعتبر است.", None

            # Metadata info for user confirmation dialog
            info = {
                "backup_type": "پیشرفته (جامع)" if doc.get("backup_type") == "ADVANCED" else "عادی",
                "created_at": doc.get("created_at", "نامشخص"),
                "total_components": doc.get("total_components", len(payload.get("components", []))),
                "has_custom_categories": bool(payload.get("custom_categories")),
                "has_custom_packages": bool(payload.get("custom_packages")),
                "doc": doc
            }

            return True, "فایل پشتیبان دارای امضای معتبر و تاییدشده است.", info

        except json.JSONDecodeError:
            return False, "فایل انتخابی یک فایل متنی یا JSON استاندارد نیست.", None
        except Exception as e:
            return False, f"خطا در خواندن فایل پشتیبان: {str(e)}", None

    @classmethod
    def restore_backup(cls, db: Database, file_path: str) -> Tuple[bool, str]:
        """
        Restore entire database state from a verified digitally-signed backup file.
        """
        is_valid, reason, info = cls.verify_backup_file(file_path)
        if not is_valid or not info:
            return False, reason

        doc = info["doc"]
        payload = doc["payload"]
        components = payload.get("components", [])
        history = payload.get("stock_history", [])
        is_adv = doc.get("backup_type") == "ADVANCED"

        try:
            with db._get_connection() as conn:
                cursor = conn.cursor()

                # 1. Safely purge existing data tables
                cursor.execute("DELETE FROM stock_history")
                cursor.execute("DELETE FROM components")

                # 2. Insert components
                for c in components:
                    cursor.execute("""
                        INSERT INTO components (
                            id, name, value, package, category, quantity,
                            min_alert, drawers, description, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        c.get("id"),
                        c.get("name", ""),
                        c.get("value", ""),
                        c.get("package", "—"),
                        c.get("category", "—"),
                        c.get("quantity", 0),
                        c.get("min_alert", 10),
                        c.get("drawers", ""),
                        c.get("description", ""),
                        c.get("created_at", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                        c.get("updated_at", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    ))

                # 3. Insert transaction history
                for h in history:
                    cursor.execute("""
                        INSERT INTO stock_history (
                            id, component_id, change_type, amount, previous_qty, new_qty, drawer_number, note, timestamp
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        h.get("id"),
                        h.get("component_id"),
                        h.get("change_type", "ADD"),
                        h.get("amount", h.get("change_amount", 0)),
                        h.get("previous_qty", 0),
                        h.get("new_qty", h.get("final_quantity", 0)),
                        h.get("drawer_number"),
                        h.get("note", ""),
                        h.get("timestamp", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    ))

                # 4. In advanced mode, restore custom categories, custom packages, and settings
                if is_adv:
                    # Custom categories
                    cursor.execute("DELETE FROM custom_categories")
                    for cat_name in payload.get("custom_categories", []):
                        if cat_name and cat_name != "—":
                            cursor.execute("""
                                INSERT OR IGNORE INTO custom_categories (name, created_at)
                                VALUES (?, ?)
                            """, (cat_name, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

                    # Custom packages
                    cursor.execute("DELETE FROM custom_packages")
                    for pkg_name in payload.get("custom_packages", []):
                        if pkg_name and pkg_name != "—":
                            cursor.execute("""
                                INSERT OR IGNORE INTO custom_packages (name, created_at)
                                VALUES (?, ?)
                            """, (pkg_name, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

                    # Settings mode
                    cat_mode = payload.get("category_mode", "DEFAULT")
                    pkg_mode = payload.get("package_mode", "DEFAULT")
                    cursor.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES ('category_mode', ?)", (cat_mode,))
                    cursor.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES ('package_mode', ?)", (pkg_mode,))

                conn.commit()

            print(f"[INFO] [BACKUP] Successfully restored {len(components)} components from {file_path}")
            return True, f"بازیابی اطلاعات با موفقیت انجام شد.\nتعداد {len(components)} قلم قطعه بازیابی گردید."

        except Exception as e:
            print(f"[ERROR] [BACKUP] Failed to restore backup: {e}")
            return False, f"خطا در بازیابی اطلاعات در دیتابیس: {str(e)}"

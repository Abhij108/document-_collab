
import os
import shutil
import getpass
import mysql.connector
import bcrypt


# ==========================================
# DATABASE CONFIGURATION
# ==========================================

DB_CONFIG = {
    "host": "localhost",
    "user": "admin",
    "password": "Admin@12345",
    "database": "document_collab"
}

UPLOAD_FOLDER = "uploads"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ==========================================
# DATABASE CONNECTION
# ==========================================

def get_db():
    return mysql.connector.connect(**DB_CONFIG)


# ==========================================
# REGISTER
# ==========================================

def register():
    print("\n===== REGISTER =====")

    username = input("Username: ").strip()
    email = input("Email: ").strip()
    password = getpass.getpass("Password: ")

    if not username or not email or not password:
        print("All fields are required.")
        return

    password_hash = bcrypt.hashpw(
        password.encode(),
        bcrypt.gensalt()
    ).decode()

    db = get_db()
    cursor = db.cursor()

    try:
        query = """
        INSERT INTO users (username, email, password_hash)
        VALUES (%s, %s, %s)
        """

        cursor.execute(
            query,
            (username, email, password_hash)
        )

        db.commit()

        print("Registration successful!")

    except mysql.connector.Error as e:
        print("Registration failed:", e)

    finally:
        cursor.close()
        db.close()


# ==========================================
# LOGIN
# ==========================================

def login():
    print("\n===== LOGIN =====")

    email = input("Email: ").strip()
    password = getpass.getpass("Password: ")

    db = get_db()
    cursor = db.cursor(dictionary=True)

    query = """
    SELECT *
    FROM users
    WHERE email = %s
    """

    cursor.execute(query, (email,))
    user = cursor.fetchone()

    cursor.close()
    db.close()

    if not user:
        print("User not found.")
        return None

    if bcrypt.checkpw(
        password.encode(),
        user["password_hash"].encode()
    ):
        print(f"\nWelcome, {user['username']}!")
        return user

    print("Incorrect password.")
    return None


# ==========================================
# CREATE DOCUMENT
# ==========================================

def create_document(user):
    print("\n===== CREATE DOCUMENT =====")

    name = input("Document name: ").strip()

    if not name:
        print("Document name cannot be empty.")
        return

    print("\nEnter document content.")
    print("Type END on a new line to finish.")

    lines = []

    while True:
        line = input()

        if line == "END":
            break

        lines.append(line)

    content = "\n".join(lines)

    filename = f"{user['id']}_{name}"

    filepath = os.path.join(
        UPLOAD_FOLDER,
        filename
    )

    with open(filepath, "w", encoding="utf-8") as file:
        file.write(content)

    db = get_db()
    cursor = db.cursor()

    query = """
    INSERT INTO documents
    (owner_id, document_name, file_path, document_type)
    VALUES (%s, %s, %s, %s)
    """

    cursor.execute(
        query,
        (
            user["id"],
            name,
            filepath,
            "text"
        )
    )

    document_id = cursor.lastrowid

    # Create first version
    version_query = """
    INSERT INTO document_versions
    (document_id, user_id, version_number, file_path)
    VALUES (%s, %s, %s, %s)
    """

    cursor.execute(
        version_query,
        (
            document_id,
            user["id"],
            1,
            filepath
        )
    )

    db.commit()

    cursor.close()
    db.close()

    print(f"\nDocument created successfully!")
    print(f"Document ID: {document_id}")


# ==========================================
# UPLOAD DOCUMENT
# ==========================================

def upload_document(user):
    print("\n===== UPLOAD DOCUMENT =====")

    source = input("Enter file path: ").strip()

    if not os.path.isfile(source):
        print("File does not exist.")
        return

    name = os.path.basename(source)

    destination = os.path.join(
        UPLOAD_FOLDER,
        f"{user['id']}_{name}"
    )

    shutil.copy2(source, destination)

    extension = os.path.splitext(name)[1]

    db = get_db()
    cursor = db.cursor()

    query = """
    INSERT INTO documents
    (owner_id, document_name, file_path, document_type)
    VALUES (%s, %s, %s, %s)
    """

    cursor.execute(
        query,
        (
            user["id"],
            name,
            destination,
            extension
        )
    )

    document_id = cursor.lastrowid

    version_query = """
    INSERT INTO document_versions
    (document_id, user_id, version_number, file_path)
    VALUES (%s, %s, %s, %s)
    """

    cursor.execute(
        version_query,
        (
            document_id,
            user["id"],
            1,
            destination
        )
    )

    db.commit()

    cursor.close()
    db.close()

    print("File uploaded successfully.")
    print(f"Document ID: {document_id}")


# ==========================================
# MY DOCUMENTS
# ==========================================

def my_documents(user):
    print("\n===== MY DOCUMENTS =====")

    db = get_db()
    cursor = db.cursor(dictionary=True)

    query = """
    SELECT id, document_name, document_type,
           created_at, updated_at
    FROM documents
    WHERE owner_id = %s
    ORDER BY created_at DESC
    """

    cursor.execute(query, (user["id"],))

    documents = cursor.fetchall()

    cursor.close()
    db.close()

    if not documents:
        print("You have no documents.")
        return

    for doc in documents:
        print(
            f"\nID: {doc['id']}"
            f"\nName: {doc['document_name']}"
            f"\nType: {doc['document_type']}"
            f"\nCreated: {doc['created_at']}"
            f"\nUpdated: {doc['updated_at']}"
        )


# ==========================================
# SHARED DOCUMENTS
# ==========================================

def shared_documents(user):
    print("\n===== SHARED WITH ME =====")

    db = get_db()
    cursor = db.cursor(dictionary=True)

    query = """
    SELECT
        d.id,
        d.document_name,
        u.username AS owner,
        p.permission
    FROM document_permissions p

    JOIN documents d
        ON p.document_id = d.id

    JOIN users u
        ON d.owner_id = u.id

    WHERE p.user_id = %s
    """

    cursor.execute(query, (user["id"],))

    documents = cursor.fetchall()

    cursor.close()
    db.close()

    if not documents:
        print("No documents have been shared with you.")
        return

    for doc in documents:
        print(
            f"\nID: {doc['id']}"
            f"\nName: {doc['document_name']}"
            f"\nOwner: {doc['owner']}"
            f"\nPermission: {doc['permission']}"
        )


# ==========================================
# SHARE DOCUMENT
# ==========================================

def share_document(user):
    print("\n===== SHARE DOCUMENT =====")

    try:
        document_id = int(
            input("Document ID: ")
        )
    except ValueError:
        print("Invalid document ID.")
        return

    email = input(
        "User email: "
    ).strip()

    print("\n1. Viewer")
    print("2. Editor")

    choice = input("Permission: ")

    if choice == "1":
        permission = "viewer"
    elif choice == "2":
        permission = "editor"
    else:
        print("Invalid permission.")
        return

    db = get_db()
    cursor = db.cursor(dictionary=True)

    # Check ownership
    cursor.execute(
        """
        SELECT id
        FROM documents
        WHERE id = %s
        AND owner_id = %s
        """,
        (document_id, user["id"])
    )

    document = cursor.fetchone()

    if not document:
        print("You don't own this document.")
        cursor.close()
        db.close()
        return

    # Find user
    cursor.execute(
        """
        SELECT id, username
        FROM users
        WHERE email = %s
        """,
        (email,)
    )

    target_user = cursor.fetchone()

    if not target_user:
        print("User not found.")
        cursor.close()
        db.close()
        return

    if target_user["id"] == user["id"]:
        print("You cannot share a document with yourself.")
        cursor.close()
        db.close()
        return

    # Insert permission
    try:
        cursor.execute(
            """
            INSERT INTO document_permissions
            (document_id, user_id, permission)
            VALUES (%s, %s, %s)
            """,
            (
                document_id,
                target_user["id"],
                permission
            )
        )

        db.commit()

        print(
            f"Document shared with "
            f"{target_user['username']} "
            f"as {permission}."
        )

    except mysql.connector.Error:
        print(
            "This user already has permission "
            "for this document."
        )

    cursor.close()
    db.close()


# ==========================================
# CHANGE PERMISSION
# ==========================================

def change_permission(user):
    print("\n===== CHANGE PERMISSION =====")

    try:
        document_id = int(
            input("Document ID: ")
        )
    except ValueError:
        print("Invalid document ID.")
        return

    email = input("User email: ").strip()

    print("\n1. Viewer")
    print("2. Editor")

    choice = input("New permission: ")

    if choice == "1":
        permission = "viewer"
    elif choice == "2":
        permission = "editor"
    else:
        print("Invalid permission.")
        return

    db = get_db()
    cursor = db.cursor()

    # Check ownership
    cursor.execute(
        """
        SELECT id
        FROM documents
        WHERE id = %s
        AND owner_id = %s
        """,
        (document_id, user["id"])
    )

    if not cursor.fetchone():
        print("You don't own this document.")
        cursor.close()
        db.close()
        return

    cursor.execute(
        """
        SELECT id
        FROM users
        WHERE email = %s
        """,
        (email,)
    )

    target_user = cursor.fetchone()

    if not target_user:
        print("User not found.")
        cursor.close()
        db.close()
        return

    cursor.execute(
        """
        UPDATE document_permissions
        SET permission = %s
        WHERE document_id = %s
        AND user_id = %s
        """,
        (
            permission,
            document_id,
            target_user[0]
        )
    )

    db.commit()

    if cursor.rowcount == 0:
        print("No permission record found.")
    else:
        print("Permission updated.")

    cursor.close()
    db.close()


# ==========================================
# REMOVE PERMISSION
# ==========================================

def remove_permission(user):
    print("\n===== REMOVE PERMISSION =====")

    try:
        document_id = int(
            input("Document ID: ")
        )
    except ValueError:
        print("Invalid document ID.")
        return

    email = input("User email: ").strip()

    db = get_db()
    cursor = db.cursor()

    cursor.execute(
        """
        SELECT id
        FROM documents
        WHERE id = %s
        AND owner_id = %s
        """,
        (document_id, user["id"])
    )

    if not cursor.fetchone():
        print("You don't own this document.")
        cursor.close()
        db.close()
        return

    cursor.execute(
        """
        SELECT id
        FROM users
        WHERE email = %s
        """,
        (email,)
    )

    target_user = cursor.fetchone()

    if not target_user:
        print("User not found.")
        cursor.close()
        db.close()
        return

    cursor.execute(
        """
        DELETE FROM document_permissions
        WHERE document_id = %s
        AND user_id = %s
        """,
        (
            document_id,
            target_user[0]
        )
    )

    db.commit()

    if cursor.rowcount == 0:
        print("Permission not found.")
    else:
        print("Access removed.")

    cursor.close()
    db.close()


# ==========================================
# CHECK DOCUMENT ACCESS
# ==========================================

def get_document_access(user_id, document_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)

    # Owner
    cursor.execute(
        """
        SELECT *
        FROM documents
        WHERE id = %s
        AND owner_id = %s
        """,
        (document_id, user_id)
    )

    document = cursor.fetchone()

    if document:
        cursor.close()
        db.close()
        return document, "owner"

    # Shared permission
    cursor.execute(
        """
        SELECT
            d.*,
            p.permission
        FROM documents d

        JOIN document_permissions p
            ON d.id = p.document_id

        WHERE d.id = %s
        AND p.user_id = %s
        """,
        (document_id, user_id)
    )

    document = cursor.fetchone()

    cursor.close()
    db.close()

    if document:
        return document, document["permission"]

    return None, None


# ==========================================
# VIEW DOCUMENT
# ==========================================

def view_document(user):
    print("\n===== VIEW DOCUMENT =====")

    try:
        document_id = int(
            input("Document ID: ")
        )
    except ValueError:
        print("Invalid ID.")
        return

    document, permission = get_document_access(
        user["id"],
        document_id
    )

    if not document:
        print("You don't have access to this document.")
        return

    filepath = document["file_path"]

    if not os.path.exists(filepath):
        print("File not found.")
        return

    try:
        with open(
            filepath,
            "r",
            encoding="utf-8"
        ) as file:
            content = file.read()

        print("\n========== DOCUMENT ==========\n")
        print(content)
        print("\n==============================")

        print(f"\nAccess: {permission}")

    except UnicodeDecodeError:
        print(
            "This file cannot be displayed as text."
        )


# ==========================================
# EDIT DOCUMENT
# ==========================================

def edit_document(user):
    print("\n===== EDIT DOCUMENT =====")

    try:
        document_id = int(
            input("Document ID: ")
        )
    except ValueError:
        print("Invalid ID.")
        return

    document, permission = get_document_access(
        user["id"],
        document_id
    )

    if not document:
        print("You don't have access.")
        return

    if permission == "viewer":
        print("You only have viewer permission.")
        return

    filepath = document["file_path"]

    if not os.path.exists(filepath):
        print("File not found.")
        return

    print("\nEnter new content.")
    print("Type END on a new line to save.")

    lines = []

    while True:
        line = input()

        if line == "END":
            break

        lines.append(line)

    content = "\n".join(lines)

    with open(
        filepath,
        "w",
        encoding="utf-8"
    ) as file:
        file.write(content)

    db = get_db()
    cursor = db.cursor()

    # Get latest version
    cursor.execute(
        """
        SELECT MAX(version_number)
        FROM document_versions
        WHERE document_id = %s
        """,
        (document_id,)
    )

    result = cursor.fetchone()

    latest_version = result[0] or 0

    new_version = latest_version + 1

    cursor.execute(
        """
        INSERT INTO document_versions
        (document_id, user_id, version_number, file_path)
        VALUES (%s, %s, %s, %s)
        """,
        (
            document_id,
            user["id"],
            new_version,
            filepath
        )
    )

    db.commit()

    cursor.close()
    db.close()

    print(
        f"Document updated."
        f" Version: {new_version}"
    )


# ==========================================
# DOWNLOAD DOCUMENT
# ==========================================

def download_document(user):
    print("\n===== DOWNLOAD DOCUMENT =====")

    try:
        document_id = int(
            input("Document ID: ")
        )
    except ValueError:
        print("Invalid ID.")
        return

    document, permission = get_document_access(
        user["id"],
        document_id
    )

    if not document:
        print("You don't have access.")
        return

    source = document["file_path"]

    if not os.path.exists(source):
        print("File not found.")
        return

    destination = input(
        "Save as: "
    ).strip()

    try:
        shutil.copy2(
            source,
            destination
        )

        print("Document downloaded.")

    except Exception as e:
        print("Download failed:", e)


# ==========================================
# DASHBOARD
# ==========================================

def dashboard(user):

    while True:

        print("\n")
        print("=" * 40)
        print(" DOCUMENT COLLABORATION TOOL")
        print("=" * 40)

        print(f"Logged in as: {user['username']}")

        print("\n1. Create Document")
        print("2. Upload Document")
        print("3. My Documents")
        print("4. Shared With Me")
        print("5. View Document")
        print("6. Edit Document")
        print("7. Share Document")
        print("8. Change Permission")
        print("9. Remove Permission")
        print("10. Download Document")
        print("11. Logout")

        choice = input("\nChoose option: ")

        if choice == "1":
            create_document(user)

        elif choice == "2":
            upload_document(user)

        elif choice == "3":
            my_documents(user)

        elif choice == "4":
            shared_documents(user)

        elif choice == "5":
            view_document(user)

        elif choice == "6":
            edit_document(user)

        elif choice == "7":
            share_document(user)

        elif choice == "8":
            change_permission(user)

        elif choice == "9":
            remove_permission(user)

        elif choice == "10":
            download_document(user)

        elif choice == "11":
            print("Logged out.")
            break

        else:
            print("Invalid option.")


# ==========================================
# MAIN MENU
# ==========================================

def main():

    while True:

        print("\n")
        print("=" * 40)
        print(" DOCUMENT COLLABORATION TOOL")
        print("=" * 40)

        print("\n1. Register")
        print("2. Login")
        print("3. Exit")

        choice = input("\nChoose option: ")

        if choice == "1":
            register()

        elif choice == "2":

            user = login()

            if user:
                dashboard(user)

        elif choice == "3":
            print("Goodbye!")
            break

        else:
            print("Invalid option.")


if __name__ == "__main__":
    main()

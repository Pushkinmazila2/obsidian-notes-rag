#!/usr/bin/env python3
"""Test script to verify CouchDB note reconstruction."""

import logging
from src.obsidian_rag.couch_source import CouchDBClient

# Enable debug logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_reconstruction():
    """Test reconstructing a note from CouchDB."""
    
    # TODO: Update these with your actual CouchDB credentials
    client = CouchDBClient(
        couchdb_url="http://localhost:5984",
        db="obsidian",
        username="admin",
        password="password",
    )
    
    # Test with a specific note
    test_note_id = "работа/synology управления правами доступа.md"
    
    print(f"\n{'='*60}")
    print(f"Testing note reconstruction: {test_note_id}")
    print(f"{'='*60}\n")
    
    # Fetch metadata
    meta = client.get_doc(test_note_id)
    if not meta:
        print(f"❌ Note not found: {test_note_id}")
        return
    
    print(f"✓ Metadata found:")
    print(f"  Type: {meta.get('type')}")
    print(f"  Path: {meta.get('path')}")
    print(f"  Children: {len(meta.get('children', []))} chunks")
    print(f"  Size: {meta.get('size')} bytes")
    print(f"  Modified: {meta.get('mtime')}")
    
    # Reconstruct content
    print(f"\nReconstructing note...")
    content = client.reconstruct_note(meta)
    
    print(f"\n{'='*60}")
    print(f"Reconstructed content ({len(content)} chars):")
    print(f"{'='*60}")
    print(content)
    print(f"{'='*60}\n")
    
    # Test with all notes
    print(f"\n{'='*60}")
    print("Testing all notes in database...")
    print(f"{'='*60}\n")
    
    count = 0
    errors = 0
    
    for meta in client.iter_note_metadata():
        count += 1
        note_path = meta.get("path") or meta["_id"]
        try:
            content = client.reconstruct_note(meta)
            if content.strip():
                print(f"✓ [{count}] {note_path} ({len(content)} chars)")
            else:
                print(f"⚠ [{count}] {note_path} (empty)")
                errors += 1
        except Exception as e:
            print(f"❌ [{count}] {note_path}: {e}")
            errors += 1
    
    print(f"\n{'='*60}")
    print(f"Summary: {count} notes processed, {errors} errors")
    print(f"{'='*60}\n")
    
    client.close()

if __name__ == "__main__":
    test_reconstruction()
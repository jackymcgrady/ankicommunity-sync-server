#!/usr/bin/env python3
"""
Schema Updater for Anki Sync Server

This module handles schema compatibility between different Anki versions
and provides dynamic field mapping for sync operations.

Major schema changes handled:
- V11: Original schema with JSON storage for decks/models
- V14: Added deck_config, config, tags tables
- V15: Added fields, templates, notetypes tables; new decks structure
- V17: Restructured tags table (WITHOUT ROWID, new columns)
- V18: Restructured graves table (new primary key, WITHOUT ROWID)
"""

import logging
import json
from typing import Dict, List, Tuple, Any, Optional

logger = logging.getLogger("ankisyncd.schema_updater")


class SchemaUpdater:
    """Handles schema compatibility and field mapping for different Anki versions."""
    
    def __init__(self, col):
        self.col = col
        self._field_mappings = {}
        self._schema_version = None
        self._table_exists_cache = {}
        self._detect_schema_version()
    
    def _detect_schema_version(self):
        """Detect the current schema version and set up field mappings."""
        try:
            # Get schema version from collection - scm is a method, not an attribute
            if hasattr(self.col, 'scm'):
                self.schema_version = self.col.scm()  # Call as method
            else:
                # Fallback for collections without scm method
                self.schema_version = self.col.db.scalar("select scm from col") or 0
            
            self.anki_version = getattr(self.col, 'ver', 'unknown')
            
            # Detect actual schema version by checking table structures
            self._schema_version = self._detect_actual_schema_version()
            
            logger.info(f"Detected Anki version: {self.anki_version}, Schema: {self.schema_version}, Actual: {self._schema_version}")
            
            # Set up field mappings based on detected version
            self._setup_field_mappings()
            
        except Exception as e:
            logger.warning(f"Could not detect schema version: {e}")
            # Fall back to legacy mappings and set default schema version
            self._schema_version = 11  # Default to V11 (legacy schema)
            self.schema_version = 11
            self.anki_version = 'unknown'
            self._setup_legacy_mappings()
            logger.info(f"Using fallback schema version {self._schema_version}")
    
    def _detect_actual_schema_version(self) -> int:
        """Detect actual schema version by checking table structures."""
        try:
            # Check for V18 features (restructured graves table)
            if self._table_exists('graves'):
                graves_info = self.col.db.execute("PRAGMA table_info(graves)").fetchall()
                # V18 graves has (oid, type) as primary key
                if len(graves_info) == 3:  # oid, type, usn
                    return 18
            
            # Check for V17 features (restructured tags table)
            if self._table_exists('tags'):
                tags_info = self.col.db.execute("PRAGMA table_info(tags)").fetchall()
                # V17 tags has collapsed and config columns
                if len(tags_info) >= 4:  # tag, usn, collapsed, config
                    return 17
            
            # Check for V15 features (fields, templates, notetypes tables)
            if (self._table_exists('fields') and 
                self._table_exists('templates') and 
                self._table_exists('notetypes')):
                return 15
            
            # Check for V14 features (deck_config, config tables)
            if (self._table_exists('deck_config') and 
                self._table_exists('config')):
                return 14
            
            # Default to V11 (legacy schema)
            return 11
            
        except Exception as e:
            logger.warning(f"Could not detect actual schema version: {e}")
            return 11
    
    def _table_exists(self, table_name: str) -> bool:
        """Check if a table exists in the database."""
        if table_name not in self._table_exists_cache:
            try:
                result = self.col.db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (table_name,)
                ).fetchone()
                self._table_exists_cache[table_name] = result is not None
            except Exception:
                self._table_exists_cache[table_name] = False
        return self._table_exists_cache[table_name]
    
    def _setup_field_mappings(self):
        """Set up field mappings for different table structures."""
        
        # Get actual table schemas from the database
        self._field_mappings = {
            'cards': self._get_table_fields('cards'),
            'notes': self._get_table_fields('notes'),
            'revlog': self._get_table_fields('revlog'),
        }
        
        # Handle schema-specific table mappings
        # Always include graves table since it exists in all schema versions
        if self._table_exists('graves'):
            self._field_mappings['graves'] = self._get_table_fields('graves')
        else:
            # Provide default graves mapping if table doesn't exist
            self._field_mappings['graves'] = self._get_legacy_fields('graves')
        
        if self._schema_version >= 17:
            self._field_mappings['tags'] = self._get_table_fields('tags')
        
        if self._schema_version >= 15:
            self._field_mappings.update({
                'fields': self._get_table_fields('fields'),
                'templates': self._get_table_fields('templates'),
                'notetypes': self._get_table_fields('notetypes'),
                'decks': self._get_table_fields('decks'),
            })
        
        if self._schema_version >= 14:
            self._field_mappings.update({
                'deck_config': self._get_table_fields('deck_config'),
                'config': self._get_table_fields('config'),
            })
        
        logger.info(f"Field mappings for schema V{self._schema_version}: {list(self._field_mappings.keys())}")
        
        # Debug: Check revlog table handling for collections with review history
        if 'revlog' in self._field_mappings:
            revlog_fields = self._field_mappings['revlog']
            logger.info(f"🔍 DEBUG: Revlog table has {len(revlog_fields)} fields: {revlog_fields}")
            
            # Check if revlog table has data (indicates review history)
            try:
                revlog_count = self.col.db.scalar("SELECT COUNT(*) FROM revlog")
                logger.info(f"🔍 DEBUG: Collection has {revlog_count} review history entries")
                if revlog_count > 0:
                    logger.info("🔍 DEBUG: This collection contains review history - extra attention needed for sync compatibility")
            except Exception as e:
                logger.warning(f"Could not check revlog count: {e}")
        else:
            logger.error("❌ DEBUG: No revlog field mapping found - this could cause sync issues")
    
    def _get_table_fields(self, table_name: str) -> List[str]:
        """Get the actual field names for a table from the database."""
        try:
            # Get table schema - fetchall() returns a list, not a cursor
            schema_info = self.col.db.execute(f"PRAGMA table_info({table_name})").fetchall()
            fields = [row[1] for row in schema_info]  # row[1] is the column name
            logger.debug(f"Table {table_name} has fields: {fields}")
            return fields
        except Exception as e:
            logger.error(f"Could not get fields for table {table_name}: {e}")
            return self._get_legacy_fields(table_name)
    
    def _get_legacy_fields(self, table_name: str) -> List[str]:
        """Get legacy field mappings for older Anki versions."""
        legacy_mappings = {
            'cards': ['id', 'nid', 'did', 'ord', 'mod', 'usn', 'type', 'queue', 
                     'due', 'ivl', 'factor', 'reps', 'lapses', 'left', 'odue', 
                     'odid', 'flags', 'data'],
            'notes': ['id', 'guid', 'mid', 'mod', 'usn', 'tags', 'flds', 
                     'sfld', 'csum', 'flags', 'data'],
            'revlog': ['id', 'cid', 'usn', 'ease', 'ivl', 'lastIvl', 'factor', 
                      'time', 'type'],
            'graves': ['usn', 'oid', 'type'],  # V11 schema
            'tags': ['tag', 'usn'],  # V14 schema
        }
        return legacy_mappings.get(table_name, [])
    
    def _setup_legacy_mappings(self):
        """Set up legacy field mappings for older Anki versions."""
        self._field_mappings = {
            'cards': self._get_legacy_fields('cards'),
            'notes': self._get_legacy_fields('notes'),
            'revlog': self._get_legacy_fields('revlog'),
            'graves': self._get_legacy_fields('graves'),
            'tags': self._get_legacy_fields('tags'),
        }
    
    def get_query_fields(self, table_name: str) -> str:
        """Get the field list for SELECT queries."""
        fields = self._field_mappings.get(table_name, [])
        if not fields:
            logger.error(f"No field mapping found for table {table_name}")
            return "*"
        
        # Handle special cases for sync queries
        if table_name == 'notes':
            # Notes table has some special handling in the original code
            # Replace empty strings with actual field names if they exist
            query_fields = []
            for field in fields:
                if field in ['sfld', 'csum']:
                    # These might be empty in legacy queries but are real fields
                    query_fields.append(field)
                else:
                    query_fields.append(field)
            return ', '.join(query_fields)
        
        return ', '.join(fields)
    
    def get_insert_placeholders(self, table_name: str) -> str:
        """Get the placeholder string for INSERT queries."""
        field_count = len(self._field_mappings.get(table_name, []))
        if field_count == 0:
            logger.error(f"No fields found for table {table_name}")
            return "?"
        
        return ','.join(['?'] * field_count)
    
    def validate_row_data(self, table_name: str, row_data: Tuple) -> Tuple:
        """Validate and adjust row data to match the expected schema."""
        expected_fields = self._field_mappings.get(table_name, [])
        expected_count = len(expected_fields)
        actual_count = len(row_data)
        
        if actual_count == expected_count:
            return row_data
        
        logger.warning(f"Field count mismatch for {table_name}: expected {expected_count}, got {actual_count}")
        
        # Try to adjust the data
        if actual_count < expected_count:
            # Pad with None values
            padded_data = list(row_data) + [None] * (expected_count - actual_count)
            logger.info(f"Padded {table_name} row data from {actual_count} to {expected_count} fields")
            return tuple(padded_data)
        else:
            # Truncate extra fields
            truncated_data = row_data[:expected_count]
            logger.info(f"Truncated {table_name} row data from {actual_count} to {expected_count} fields")
            return truncated_data
    
    def get_field_count(self, table_name: str) -> int:
        """Get the expected field count for a table."""
        return len(self._field_mappings.get(table_name, []))
    
    def is_compatible_schema(self) -> bool:
        """Check if the current schema is compatible with the sync server."""
        try:
            # Basic compatibility checks
            required_tables = ['cards', 'notes', 'revlog', 'graves']
            for table in required_tables:
                if not self._field_mappings.get(table):
                    logger.error(f"Missing or empty field mapping for required table: {table}")
                    return False
            
            # Check minimum field counts
            min_field_counts = {
                'cards': 15,  # Minimum required fields
                'notes': 8,   # Minimum required fields
                'revlog': 8   # Minimum required fields
            }
            
            for table, min_count in min_field_counts.items():
                actual_count = len(self._field_mappings.get(table, []))
                if actual_count < min_count:
                    logger.error(f"Table {table} has {actual_count} fields, minimum {min_count} required")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Schema compatibility check failed: {e}")
            return False
    
    def get_schema_version(self) -> int:
        """Get the detected schema version."""
        return self._schema_version or 11
    
    def supports_table(self, table_name: str) -> bool:
        """Check if the current schema supports a specific table."""
        return table_name in self._field_mappings
    
    def convert_to_modern_format(self, table_name: str, row_data: Tuple) -> Dict[str, Any]:
        """Convert row data to modern structured format (CardEntry/NoteEntry style)."""
        fields = self._field_mappings.get(table_name, [])
        if not fields or len(fields) != len(row_data):
            logger.warning(f"Cannot convert {table_name} to modern format: field mismatch")
            return {}
        
        # Create structured data
        result = {}
        for i, field in enumerate(fields):
            value = row_data[i] if i < len(row_data) else None
            
            # Handle special field mappings for modern format
            if table_name == 'cards':
                field_map = {
                    'nid': 'note_id',
                    'did': 'deck_id', 
                    'ord': 'template_idx',
                    'mod': 'mtime',
                    'type': 'ctype',
                    'ivl': 'interval',
                    'factor': 'ease_factor',
                    'odue': 'original_due',
                    'odid': 'original_deck_id'
                }
                result[field_map.get(field, field)] = value
            elif table_name == 'notes':
                field_map = {
                    'mid': 'ntid',  # notetype id
                    'mod': 'mtime',
                    'flds': 'fields'
                }
                result[field_map.get(field, field)] = value
            else:
                result[field] = value
        
        return result
    
    def needs_data_migration(self) -> bool:
        """Check if data migration is needed between JSON and table storage."""
        # Handle case where schema version detection failed
        if self._schema_version is None:
            logger.warning("Schema version is None in needs_data_migration, defaulting to False")
            return False
            
        # Migration needed if we have V15+ schema but old JSON data
        if self._schema_version >= 15:
            # Check if we still have JSON data in col table
            try:
                col_data = self.col.db.execute("SELECT models, decks FROM col").fetchone()
                if col_data and (col_data[0] != '{}' or col_data[1] != '{}'):
                    return True
            except Exception as e:
                logger.warning(f"Could not check for migration needs: {e}")
        return False
    
    def get_sync_version_for_schema(self) -> int:
        """Get the appropriate sync version for the current schema."""
        # Handle case where schema version detection failed
        if self._schema_version is None:
            logger.warning("Schema version is None, defaulting to sync version 10")
            return 10  # Default to V10 for compatibility
        
        # Based on Anki's version.rs mapping
        if self._schema_version >= 18:
            return 11  # SYNC_VERSION_11_DIRECT_POST
        else:
            return 10  # SYNC_VERSION_10_V2_TIMEZONE (maps to SchemaV11)
    
    def migrate_data_if_needed(self) -> bool:
        """Migrate data between JSON and table storage if needed."""
        if not self.needs_data_migration():
            return False
        
        logger.info("Starting data migration from JSON to table storage")
        
        try:
            # Migrate models/notetypes from JSON to tables
            if self._schema_version >= 15:
                self._migrate_models_to_notetypes()
            
            # Migrate decks from JSON to tables  
            if self._schema_version >= 15:
                self._migrate_decks_to_tables()
            
            # Clear JSON data after successful migration
            self.col.db.execute("UPDATE col SET models='{}', decks='{}'")
            
            logger.info("Data migration completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Data migration failed: {e}")
            return False
    
    def _migrate_models_to_notetypes(self):
        """Migrate models from JSON storage to notetypes/fields/templates tables."""
        try:
            # Get models from JSON
            models_json = self.col.db.scalar("SELECT models FROM col")
            if not models_json or models_json == '{}':
                return
            
            models = json.loads(models_json)
            
            for model_id, model in models.items():
                # Insert into notetypes table
                self.col.db.execute("""
                    INSERT OR REPLACE INTO notetypes (id, name, mtime_secs, usn, config)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    int(model_id),
                    model.get('name', ''),
                    model.get('mod', 0),
                    model.get('usn', 0),
                    json.dumps(model).encode('utf-8')  # Store full config as blob
                ))
                
                # Insert fields
                for field in model.get('flds', []):
                    self.col.db.execute("""
                        INSERT OR REPLACE INTO fields (ntid, ord, name, config)
                        VALUES (?, ?, ?, ?)
                    """, (
                        int(model_id),
                        field.get('ord', 0),
                        field.get('name', ''),
                        json.dumps(field).encode('utf-8')
                    ))
                
                # Insert templates
                for template in model.get('tmpls', []):
                    self.col.db.execute("""
                        INSERT OR REPLACE INTO templates (ntid, ord, name, mtime_secs, usn, config)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        int(model_id),
                        template.get('ord', 0),
                        template.get('name', ''),
                        model.get('mod', 0),
                        model.get('usn', 0),
                        json.dumps(template).encode('utf-8')
                    ))
            
            logger.info(f"Migrated {len(models)} models to notetypes tables")
            
        except Exception as e:
            logger.error(f"Failed to migrate models: {e}")
            raise
    
    def _migrate_decks_to_tables(self):
        """Migrate decks from JSON storage to decks table."""
        try:
            # Get decks from JSON
            decks_json = self.col.db.scalar("SELECT decks FROM col")
            if not decks_json or decks_json == '{}':
                return
            
            decks = json.loads(decks_json)
            
            for deck_id, deck in decks.items():
                # Insert into decks table
                self.col.db.execute("""
                    INSERT OR REPLACE INTO decks (id, name, mtime_secs, usn, common, kind)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    int(deck_id),
                    deck.get('name', ''),
                    deck.get('mod', 0),
                    deck.get('usn', 0),
                    json.dumps(deck).encode('utf-8'),  # Store as common blob
                    b''  # Empty kind blob for now
                ))
            
            logger.info(f"Migrated {len(decks)} decks to decks table")
            
        except Exception as e:
            logger.error(f"Failed to migrate decks: {e}")
            raise
    
    def convert_to_legacy_format(self, table_name: str, modern_data: Dict[str, Any]) -> Tuple:
        """Convert modern structured data back to legacy tuple format."""
        if table_name == 'cards':
            # Convert CardEntry back to legacy tuple
            legacy_fields = self._get_legacy_fields('cards')
            values = []
            
            field_map = {
                'note_id': 'nid',
                'deck_id': 'did',
                'template_idx': 'ord',
                'mtime': 'mod',
                'ctype': 'type',
                'interval': 'ivl',
                'ease_factor': 'factor',
                'original_due': 'odue',
                'original_deck_id': 'odid'
            }
            
            for field in legacy_fields:
                # Map modern field names back to legacy
                modern_field = field
                for modern, legacy in field_map.items():
                    if legacy == field:
                        modern_field = modern
                        break
                
                values.append(modern_data.get(modern_field, modern_data.get(field, None)))
            
            return tuple(values)
        
        elif table_name == 'notes':
            # Convert NoteEntry back to legacy tuple
            legacy_fields = self._get_legacy_fields('notes')
            values = []
            
            field_map = {
                'ntid': 'mid',
                'mtime': 'mod',
                'fields': 'flds'
            }
            
            for field in legacy_fields:
                # Map modern field names back to legacy
                modern_field = field
                for modern, legacy in field_map.items():
                    if legacy == field:
                        modern_field = modern
                        break
                
                values.append(modern_data.get(modern_field, modern_data.get(field, None)))
            
            return tuple(values)
        
        # For other tables, just extract values in field order
        fields = self._field_mappings.get(table_name, [])
        return tuple(modern_data.get(field, None) for field in fields)
    
    def handle_schema_incompatibility(self, client_schema: int, server_schema: int) -> Dict[str, Any]:
        """Handle schema incompatibility between client and server."""
        logger.warning(f"Schema incompatibility: client={client_schema}, server={server_schema}")
        
        response = {
            'compatible': False,
            'requires_full_sync': False,
            'migration_needed': False,
            'error': None
        }
        
        # Determine compatibility and required actions
        if abs(client_schema - server_schema) > 7:  # Major version difference
            response['requires_full_sync'] = True
            response['error'] = f"Major schema difference (client: {client_schema}, server: {server_schema}). Full sync required."
        
        elif client_schema > server_schema:
            # Client is newer - server needs upgrade
            response['migration_needed'] = True
            response['error'] = f"Server schema ({server_schema}) is older than client ({client_schema}). Server upgrade needed."
        
        elif server_schema > client_schema:
            # Server is newer - might be compatible with downgrade
            if server_schema - client_schema <= 3:  # Minor difference
                response['compatible'] = True
                logger.info(f"Server schema ({server_schema}) newer than client ({client_schema}), but compatible")
            else:
                response['requires_full_sync'] = True
                response['error'] = f"Server schema ({server_schema}) too new for client ({client_schema}). Client upgrade needed."
        
        return response
    
    def get_schema_compatibility_info(self) -> Dict[str, Any]:
        """Get comprehensive schema compatibility information."""
        return {
            'detected_version': self._schema_version,
            'sync_version': self.get_sync_version_for_schema(),
            'supported_tables': list(self._field_mappings.keys()),
            'needs_migration': self.needs_data_migration(),
            'is_compatible': self.is_compatible_schema(),
            'field_counts': {table: len(fields) for table, fields in self._field_mappings.items()},
            'schema_features': {
                'has_deck_config': self.supports_table('deck_config'),
                'has_notetypes': self.supports_table('notetypes'),
                'has_fields': self.supports_table('fields'),
                'has_templates': self.supports_table('templates'),
                'restructured_tags': self._schema_version >= 17,
                'restructured_graves': self._schema_version >= 18,
            }
        } 
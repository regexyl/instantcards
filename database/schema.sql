-- InstantCards Database Schema for Supabase

-- Create enum for job status
CREATE TYPE job_status AS ENUM ('pending', 'success', 'failure');

-- Create enum for card destination
CREATE TYPE card_destination AS ENUM ('mochi');

-- Job table - tracks processing jobs
CREATE TABLE job (
    id BIGSERIAL PRIMARY KEY,
    workflow_id VARCHAR(255) UNIQUE,
    thumbnail_url TEXT,
    source_url TEXT, -- video URL or other source
    audio_url TEXT,
    status job_status NOT NULL DEFAULT 'pending',
    from_language VARCHAR(10), -- ISO 639-1 codes
    to_language VARCHAR(10),
    difficulty DECIMAL(3,2) CHECK (difficulty >= 0 AND difficulty <= 1),
    metadata JSONB, -- for flexible additional data
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Atom table (vocabulary words)
CREATE TABLE atom (
    id BIGSERIAL PRIMARY KEY,
    workflow_id VARCHAR(255) NOT NULL REFERENCES job(workflow_id) ON DELETE CASCADE,
    value TEXT NOT NULL, 
    translated_value TEXT NOT NULL,
    part_of_speech VARCHAR(50), -- noun, verb, adjective, etc.
    frequency DECIMAL(3,2) CHECK (frequency >= 0 AND frequency <= 1),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Add base_form field to atom table
ALTER TABLE atom ADD COLUMN base_form TEXT NOT NULL;

-- Block table (sentences/phrases)
CREATE TABLE block (
    id BIGSERIAL PRIMARY KEY,
    workflow_id VARCHAR(255) NOT NULL REFERENCES job(workflow_id) ON DELETE CASCADE,
    value TEXT NOT NULL, -- original text
    translated_value TEXT NOT NULL,
    start_time DECIMAL(10,3), -- timestamp in video/audio
    end_time DECIMAL(10,3),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Block-Atom relationships (many-to-many)
CREATE TABLE block_atom (
    id BIGSERIAL PRIMARY KEY,
    block_id BIGINT NOT NULL REFERENCES block(id) ON DELETE CASCADE,
    atom_id BIGINT NOT NULL REFERENCES atom(id) ON DELETE CASCADE,
    position INTEGER, -- position within the block
    UNIQUE(block_id, atom_id, position)
);

-- Card table
CREATE TABLE card (
    id BIGSERIAL PRIMARY KEY,
    workflow_id VARCHAR(255) NOT NULL REFERENCES job(workflow_id) ON DELETE CASCADE,
    type VARCHAR(10) NOT NULL CHECK (type IN ('atom', 'block')),
    atom_id BIGINT REFERENCES atom(id) ON DELETE CASCADE,
    block_id BIGINT REFERENCES block(id) ON DELETE CASCADE,
    destination card_destination NOT NULL,
    destination_id VARCHAR(255), -- ID in the destination system
    card_data JSONB, -- flexible card content storage
    status VARCHAR(50) DEFAULT 'created', -- created, synced, failed
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    -- Ensure only one of atom_id or block_id is set
    CONSTRAINT card_reference_check CHECK (
        (type = 'atom' AND atom_id IS NOT NULL AND block_id IS NULL) OR
        (type = 'block' AND block_id IS NOT NULL AND atom_id IS NULL)
    )
);

-- Create indexes for better performance
CREATE INDEX idx_job_status ON job(status);
CREATE INDEX idx_job_created_at ON job(created_at DESC);
CREATE INDEX idx_atom_workflow_id ON atom(workflow_id);
CREATE INDEX idx_atom_value ON atom(value);
CREATE INDEX idx_block_workflow_id ON block(workflow_id);
CREATE INDEX idx_block_atom_block_id ON block_atom(block_id);
CREATE INDEX idx_block_atom_atom_id ON block_atom(atom_id);
CREATE INDEX idx_card_workflow_id ON card(workflow_id);
CREATE INDEX idx_card_type ON card(type);
CREATE INDEX idx_card_atom_id ON card(atom_id);
CREATE INDEX idx_card_block_id ON card(block_id);
CREATE INDEX idx_card_destination_id ON card(destination_id);

-- Create updated_at trigger function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create triggers for tables with updated_at
CREATE TRIGGER update_job_updated_at 
    BEFORE UPDATE ON job 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_card_updated_at 
    BEFORE UPDATE ON card 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import sys
from gtts import gTTS
import markdown
from bs4 import BeautifulSoup

def clean_markdown(md_content):
    """Clean markdown content to make it more suitable for TTS"""
    # Remove code blocks
    md_content = re.sub(r'```.*?```', 'Code block omitted for audio version.', md_content, flags=re.DOTALL)
    
    # Remove inline code
    md_content = re.sub(r'`([^`]+)`', r'\1', md_content)
    
    # Remove mermaid diagrams
    md_content = re.sub(r'```mermaid.*?```', 'Diagram omitted for audio version.', md_content, flags=re.DOTALL)
    
    # Remove image references
    md_content = re.sub(r'!\[.*?\]\(.*?\)', 'Image omitted for audio version.', md_content)
    
    # Remove links but keep the text
    md_content = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', md_content)
    
    return md_content

def markdown_to_text(md_content):
    """Convert markdown to plain text for TTS"""
    # First clean the markdown
    md_content = clean_markdown(md_content)
    
    # Convert markdown to HTML
    html = markdown.markdown(md_content)
    
    # Use BeautifulSoup to extract text from HTML
    soup = BeautifulSoup(html, features="html.parser")
    
    # Get text
    text = soup.get_text()
    
    # Add pauses after headings and paragraphs
    text = re.sub(r'(#.*?)(\n)', r'\1. \2\2', text)
    text = re.sub(r'(\n\n)', r'. \1', text)
    
    return text

def convert_file_to_audio(md_file, output_dir):
    """Convert a markdown file to an audio file"""
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Get base filename without extension
    base_name = os.path.basename(md_file).replace('.md', '')
    
    # Read markdown file
    with open(md_file, 'r') as f:
        md_content = f.read()
    
    # Convert to text
    text = markdown_to_text(md_content)
    
    # Split into chunks if text is too long (gTTS has limitations)
    max_chars = 5000
    chunks = [text[i:i+max_chars] for i in range(0, len(text), max_chars)]
    
    # Convert each chunk to audio
    for i, chunk in enumerate(chunks):
        output_file = f"{output_dir}/{base_name}_part{i+1}.mp3" if len(chunks) > 1 else f"{output_dir}/{base_name}.mp3"
        print(f"Converting {md_file} to {output_file}...")
        
        # Convert to audio
        tts = gTTS(text=chunk, lang='en', slow=False)
        tts.save(output_file)
        
        print(f"Created {output_file}")

def process_directory(input_dir, output_dir):
    """Process all markdown files in a directory"""
    # Get all markdown files
    md_files = []
    for root, dirs, files in os.walk(input_dir):
        for file in files:
            if file.endswith('.md'):
                md_files.append(os.path.join(root, file))
    
    # Sort files to process index.md first
    md_files.sort(key=lambda x: 0 if x.endswith('index.md') else 1)
    
    # Process each file
    for md_file in md_files:
        # Create relative output path
        rel_path = os.path.relpath(md_file, input_dir)
        rel_dir = os.path.dirname(rel_path)
        output_path = os.path.join(output_dir, rel_dir)
        
        convert_file_to_audio(md_file, output_path)

if __name__ == "__main__":
    # Set input and output directories
    input_dir = os.path.join(os.getcwd(), "docs")
    output_dir = os.path.join(os.getcwd(), "audio_docs")
    
    # Process all markdown files
    process_directory(input_dir, output_dir)
    
    print(f"\nAll audio files have been created in {output_dir}")
    print("To listen to the documentation, start with index.mp3 and then follow the chapters in order.")

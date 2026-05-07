import React, { useState, useRef } from "react";
import { Upload, X, FileText, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useToast } from "@/context/ToastContext";

interface ResumeUploaderProps {
  jobId: string;
  onUploadSuccess: () => void;
}

export function ResumeUploader({ jobId, onUploadSuccess }: ResumeUploaderProps) {
  const { toast } = useToast();
  const [isDragging, setIsDragging] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    
    if (e.dataTransfer.files) {
      const newFiles = Array.from(e.dataTransfer.files).filter(
        (file) => file.type === "application/pdf" || file.name.endsWith(".docx")
      );
      setFiles((prev) => [...prev, ...newFiles]);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const newFiles = Array.from(e.target.files);
      setFiles((prev) => [...prev, ...newFiles]);
    }
  };

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const uploadResumes = async () => {
    if (files.length === 0) return;

    setIsUploading(true);
    const formData = new FormData();
    files.forEach((file) => {
      formData.append("files", file);
    });

    try {
      await api.post(`/jobs/${jobId}/resumes`, formData, {
        headers: {
          "Content-Type": "multipart/form-data",
        },
      });
      setFiles([]);
      onUploadSuccess();
      toast({
        variant: "success",
        title: "Resumes uploaded",
        description: "The files were uploaded and sent for parsing.",
      });
    } catch (error) {
      console.error("Upload failed", error);
      toast({
        variant: "error",
        title: "Upload failed",
        description: "We couldn't upload or parse those resumes just now.",
      });
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={cn(
          "border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-all duration-200",
          isDragging 
            ? "border-primary bg-primary/5 scale-[1.01]" 
            : "border-border/50 bg-card/30 hover:border-primary/50 hover:bg-card/50"
        )}
      >
        <input
          type="file"
          ref={fileInputRef}
          onChange={handleFileSelect}
          multiple
          accept=".pdf,.docx"
          className="hidden"
        />
        <div className="flex flex-col items-center gap-3">
          <div className="p-4 bg-primary/10 rounded-full text-primary">
            <Upload className="h-8 w-8" />
          </div>
          <div>
            <p className="text-lg font-semibold">Drop resumes here</p>
            <p className="text-sm text-muted-foreground">PDF or DOCX (max 10MB each)</p>
          </div>
        </div>
      </div>

      {files.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-medium">{files.length} file(s) selected</h4>
            <Button variant="ghost" size="sm" onClick={() => setFiles([])} disabled={isUploading}>
              Clear all
            </Button>
          </div>
          <div className="space-y-2">
            {files.map((file, i) => (
              <div key={i} className="flex items-center justify-between p-3 bg-muted/30 rounded-lg border border-border/50">
                <div className="flex items-center gap-3 overflow-hidden">
                  <FileText className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                  <span className="text-sm font-medium truncate">{file.name}</span>
                </div>
                <button 
                  onClick={(e) => { e.stopPropagation(); removeFile(i); }} 
                  className="p-1 hover:text-destructive transition-colors"
                  disabled={isUploading}
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
          <Button 
            className="w-full h-11 text-base font-semibold shadow-lg shadow-primary/20" 
            onClick={uploadResumes}
            disabled={isUploading}
          >
            {isUploading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Parsing Resumes...
              </>
            ) : (
              `Upload and Parse ${files.length} Resume(s)`
            )}
          </Button>
        </div>
      )}
    </div>
  );
}

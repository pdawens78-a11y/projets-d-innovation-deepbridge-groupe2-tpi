using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using EvilDICOM.Core.Helpers;
using EvilDICOM.Core.Interfaces;
using EvilDICOM.Core;
using System.IO;
using System.Xml.Linq;
using DeepBridgeWindowsApp.Dicom;

namespace DeepBridgeWindowsApp.DICOM
{
    public class DicomReader
    {
        private readonly string directoryPath;
        public string DirectoryPath => directoryPath;

        public DicomMetadata[] Slices { get; private set; }
        public DicomMetadata GlobalView { get; private set; }

        public DicomReader(string directoryPath)
        {
            this.directoryPath = directoryPath;
        }

        private string[] GetValidatedDicomFiles()
        {
            var dicomFiles = Directory.GetFiles(directoryPath, "*.dcm");
            if (dicomFiles.Length == 0)
                throw new FileNotFoundException("No DICOM files found in the directory.");
            return dicomFiles;
        }

        public void LoadGlobalView()
        {
            var dicomFiles = GetValidatedDicomFiles();
            var firstDicom = DICOMObject.Read(dicomFiles[0]);
            GlobalView = new DicomMetadata(firstDicom);
        }

        public void LoadAllFiles()
        {
            var dicomFiles = GetValidatedDicomFiles();
            Console.WriteLine($"Found {dicomFiles.Length} DICOM files.");

            var firstDicom = DICOMObject.Read(dicomFiles[0]);
            GlobalView = new DicomMetadata(firstDicom);

            var seriesNumber = firstDicom.FindFirst(TagHelper.SeriesNumber).DData.ToString();

            Slices = dicomFiles.Skip(1)
                .Select(f =>
                {
                    var dicomObject = DICOMObject.Read(f);
                    var currentSeriesNumber = dicomObject.FindFirst(TagHelper.SeriesNumber).DData.ToString();
                    if (currentSeriesNumber != seriesNumber)
                    {
                        throw new InvalidOperationException("All DICOM files must be part of the same series.");
                    }
                    return new DicomMetadata(dicomObject);
                })
                .OrderBy(slice => slice.SliceLocation) // Assuming SeriesTime is a property of DicomMetadata
                .ToArray();
        }
    }
}

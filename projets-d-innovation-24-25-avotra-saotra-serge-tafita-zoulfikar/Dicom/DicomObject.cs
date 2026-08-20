using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using EvilDICOM.Core.Helpers;
using EvilDICOM.Core;
using EvilDICOM.Network.DIMSE.IOD;
using System.Net.Mime;

namespace DeepBridgeWindowsApp.Dicom
{
    public class DicomMetadata
    {
        // (0020:1041)      ,Slice Location                     ,DS,1,8         ,-207.000
        public string PatientID { get; set; }
        public string PatientName { get; set; }
        public string PatientSex { get; set; }
        public string Modality { get; set; }
        public int Series { get; set; }
        public string SeriesTime { get; set; }
        public string ContentTime { get; set; }
        public int Rows { get; set; }
        public int Columns { get; set; }
        public int WindowCenter { get; set; }
        public int WindowWidth { get; set; }
        public double SliceThickness { get; set; }        // (0018,0050) DS
        public double SliceLocation { get; set; }         // (0020,1041) DS
        public double PixelSpacing { get; set; }        // (0028,0030) DS[2]
        public List<byte> PixelData { get; set; }
        public int BitsAllocated { get; set; }
        public int BitsStored { get; set; }
        public int HighBit { get; set; }
        public int PixelRepresentation { get; set; }
        public double RescaleIntercept { get; set; }
        public double RescaleSlope { get; set; }

        public DicomMetadata(DICOMObject dicomObject)
        {
            PatientID = dicomObject.FindFirst(TagHelper.PatientID)?.DData.ToString();
            PatientName = dicomObject.FindFirst(TagHelper.PatientName)?.DData.ToString();
            PatientSex = dicomObject.FindFirst(TagHelper.PatientSex)?.DData.ToString();
            Modality = dicomObject.FindFirst(TagHelper.Modality)?.DData.ToString();
            Series = Convert.ToInt32(dicomObject.FindFirst(TagHelper.SeriesNumber)?.DData ?? 0);
            SeriesTime = dicomObject.FindFirst(TagHelper.SeriesTime)?.DData.ToString();
            ContentTime = dicomObject.FindFirst(TagHelper.ContentTime)?.DData.ToString();
            Rows = Convert.ToInt32(dicomObject.FindFirst(TagHelper.Rows)?.DData ?? 0);
            Columns = Convert.ToInt32(dicomObject.FindFirst(TagHelper.Columns)?.DData ?? 0);
            WindowCenter = Convert.ToInt32(dicomObject.FindFirst(TagHelper.WindowCenter)?.DData ?? 0);
            WindowWidth = Convert.ToInt32(dicomObject.FindFirst(TagHelper.WindowWidth)?.DData ?? 0);
            SliceThickness = Convert.ToDouble(dicomObject.FindFirst(TagHelper.SliceThickness)?.DData ?? 0);
            SliceLocation = Convert.ToDouble(dicomObject.FindFirst(TagHelper.SliceLocation)?.DData ?? 0);
            PixelSpacing = Convert.ToDouble(dicomObject.FindFirst(TagHelper.PixelSpacing)?.DData.ToString().Split('\\').Select(double.Parse).ToArray()[0]);
            PixelData = (List<byte>)dicomObject.FindFirst(TagHelper.PixelData).DData_;
            BitsAllocated = Convert.ToInt32(dicomObject.FindFirst(TagHelper.BitsAllocated).DData);
            BitsStored = Convert.ToInt32(dicomObject.FindFirst(TagHelper.BitsStored).DData);
            HighBit = Convert.ToInt32(dicomObject.FindFirst(TagHelper.HighBit).DData);
            PixelRepresentation = Convert.ToInt32(dicomObject.FindFirst(TagHelper.PixelRepresentation).DData);
            RescaleIntercept = Convert.ToDouble(dicomObject.FindFirst(TagHelper.RescaleIntercept).DData);
            RescaleSlope = Convert.ToDouble(dicomObject.FindFirst(TagHelper.RescaleSlope).DData);
        }

        public void PrintInfo()
        {
            Console.WriteLine($"Series: {Series}");
            Console.WriteLine($"Series Time: {SeriesTime}");
            Console.WriteLine($"Modality: {Modality}");
            Console.WriteLine($"Rows: {Rows}");
            Console.WriteLine($"Columns: {Columns}");
            Console.WriteLine($"Window Center: {WindowCenter}");
            Console.WriteLine($"Window Width: {WindowWidth}");
            Console.WriteLine($"Slice Thickness: {SliceThickness}");
            Console.WriteLine($"Slice Location: {SliceLocation}");
            Console.WriteLine($"Pixel Spacing: {PixelSpacing} x {PixelSpacing}");
        }
    }
}

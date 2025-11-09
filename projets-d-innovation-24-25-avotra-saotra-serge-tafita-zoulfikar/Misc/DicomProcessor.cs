using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Imaging;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Forms;
using EvilDICOM.Core;
using EvilDICOM.Core.Helpers;
using EvilDICOM.Core.Modules;
using EvilDICOM.Network.Helpers;

namespace DeepBridgeWindowsApp
{
    internal class DicomProcessor
    {
        private readonly string dicomPath = @"C:\Users\Duck\Documents\Cours\M2 MBDS\Deep Bridge\dataset_chu_nice_2020_2021\1.2.840.113619.2.5.77241951.30716.1506527979.913.dcm";

        public void Run()
        {
            try
            {
                Console.WriteLine($"Loading DICOM from: {dicomPath}");
                var dicomFile = DICOMObject.Read(dicomPath);
                ProcessDicomFile(dicomFile);
                //DisplayImage(dicomFile);
                //ProcessDicomImage(dicomFile);
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Error: {ex.Message}");
            }
        }

        private void ProcessDicomFile(DICOMObject dicomFile)
        {
            // Read and display metadata
            var patientID = dicomFile.FindFirst(TagHelper.PatientID)?.DData.ToString();
            var patientName = dicomFile.FindFirst(TagHelper.PatientName)?.DData.ToString();
            var patientSex = dicomFile.FindFirst(TagHelper.PatientSex)?.DData.ToString();
            var modality = dicomFile.FindFirst(TagHelper.Modality)?.DData.ToString();
            var rows = Convert.ToInt32(dicomFile.FindFirst(TagHelper.Rows)?.DData ?? 0);
            var columns = Convert.ToInt32(dicomFile.FindFirst(TagHelper.Columns)?.DData ?? 0);
            var windowCenter = dicomFile.FindFirst(TagHelper.WindowCenter)?.DData.ToString();
            var windowWidth = dicomFile.FindFirst(TagHelper.WindowWidth)?.DData.ToString();

            // Print metadata to console
            Console.WriteLine($"Patient ID: {patientID}");
            Console.WriteLine($"Patient Name: {patientName}");
            Console.WriteLine($"Patient Sex: {patientSex}");
            Console.WriteLine($"Modality: {modality}");
            Console.WriteLine($"Rows: {rows}");
            Console.WriteLine($"Columns: {columns}");
            Console.WriteLine($"Window Center: {windowCenter}");
            Console.WriteLine($"Window Width: {windowWidth}");
            Console.Read();
        }
        
        private void DisplayImage(DICOMObject dicomFile)
        {
            try
            {
                // Get all necessary DICOM parameters
                string photo = dicomFile.FindFirst(TagHelper.PhotometricInterpretation).DData.ToString();
                ushort bitsAllocated = (ushort)dicomFile.FindFirst(TagHelper.BitsAllocated).DData;
                ushort highBit = (ushort)dicomFile.FindFirst(TagHelper.HighBit).DData;
                ushort bitsStored = (ushort)dicomFile.FindFirst(TagHelper.BitsStored).DData;
                double intercept = (double)dicomFile.FindFirst(TagHelper.RescaleIntercept).DData;
                double slope = (double)dicomFile.FindFirst(TagHelper.RescaleSlope).DData;
                ushort rows = (ushort)dicomFile.FindFirst(TagHelper.Rows).DData;
                ushort columns = (ushort)dicomFile.FindFirst(TagHelper.Columns).DData;
                ushort pixelRepresentation = (ushort)dicomFile.FindFirst(TagHelper.PixelRepresentation).DData;
                List<byte> pixelData = (List<byte>)dicomFile.FindFirst(TagHelper.PixelData).DData_;
                double window = (double)dicomFile.FindFirst(TagHelper.WindowWidth).DData;
                double level = (double)dicomFile.FindFirst(TagHelper.WindowCenter).DData;

                Console.WriteLine($"Image size: {columns}x{rows}");
                Console.WriteLine($"Window/Level: {window}/{level}");

                if (!photo.Contains("MONOCHROME"))
                {
                    Console.WriteLine("Only monochrome images are supported");
                    return;
                }

                // Process pixel data
                byte[] outPixelData = new byte[rows * columns * 4]; // RGBA
                ushort mask = (ushort)(ushort.MaxValue >> (bitsAllocated - bitsStored));
                double maxval = Math.Pow(2, bitsStored);
                int index = 0;

                for (int i = 0; i < pixelData.Count; i += 2)
                {
                    // Combine bytes into 16-bit pixel value
                    ushort gray = (ushort)((ushort)(pixelData[i]) + (ushort)(pixelData[i + 1] << 8));
                    double valgray = gray & mask; // Remove unused bits

                    // Handle signed pixels
                    if (pixelRepresentation == 1)
                    {
                        if (valgray > (maxval / 2))
                            valgray = (valgray - maxval);
                    }

                    // Apply modality LUT
                    valgray = slope * valgray + intercept;

                    // Apply window/level
                    double half = ((window - 1) / 2.0) - 0.5;
                    if (valgray <= level - half)
                        valgray = 0;
                    else if (valgray >= level + half)
                        valgray = 255;
                    else
                        valgray = ((valgray - (level - 0.5)) / (window - 1) + 0.5) * 255;

                    // Set RGBA values
                    outPixelData[index] = (byte)valgray;     // B
                    outPixelData[index + 1] = (byte)valgray; // G
                    outPixelData[index + 2] = (byte)valgray; // R
                    outPixelData[index + 3] = 255;           // A

                    index += 4;
                }

                // Create and display image
                Image image = ImageFromRawBgraArray(outPixelData, columns, rows);

                Form form = new Form
                {
                    Text = "DICOM Viewer",
                    Size = new Size(600, 600)
                };

                PictureBox pictureBox = new PictureBox
                {
                    Dock = DockStyle.Fill,
                    SizeMode = PictureBoxSizeMode.Zoom,
                    Image = image
                };

                form.Controls.Add(pictureBox);
                form.Show();
                Application.Run(form);
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Error in DisplayImage: {ex.Message}");
                Console.WriteLine($"Stack Trace: {ex.StackTrace}");
            }
        }
        
        private void ProcessDicomImage(DICOMObject dicomFile)
        {
            var photo = dicomFile.FindFirst(TagHelper.PhotometricInterpretation).DData.ToString();
            Console.WriteLine($"Photo: {photo}");

            // Read and display metadata
            var patientID = dicomFile.FindFirst(TagHelper.PatientID)?.DData.ToString();
            var patientName = dicomFile.FindFirst(TagHelper.PatientName)?.DData.ToString();
            var patientSex = dicomFile.FindFirst(TagHelper.PatientSex)?.DData.ToString();
            var modality = dicomFile.FindFirst(TagHelper.Modality)?.DData.ToString();
            var rows = Convert.ToInt32(dicomFile.FindFirst(TagHelper.Rows)?.DData ?? 0);
            var columns = Convert.ToInt32(dicomFile.FindFirst(TagHelper.Columns)?.DData ?? 0);
            var windowCenter = dicomFile.FindFirst(TagHelper.WindowCenter)?.DData.ToString();
            var windowWidth = dicomFile.FindFirst(TagHelper.WindowWidth)?.DData.ToString();

            var pixelData = dicomFile.FindFirst(TagHelper.PixelData).DData_;
            var pixelDataArray = pixelData.Cast<byte>().ToArray();
            Console.WriteLine($"Pixel data length: {pixelDataArray.Length}");
        }

        private void ShowDicomImage(byte[] pixelData, int columns, int rows)
        {
            // Convert raw BGRA pixel data to an Image
            var image = ImageFromRawBgraArray(pixelData, columns, rows);

            // Create a new form to display the image
            var form = new Form
            {
                Text = "DICOM Viewer",
                Size = new Size(600, 600)
            };

            var pictureBox = new PictureBox
            {
                Dock = DockStyle.Fill,
                SizeMode = PictureBoxSizeMode.Zoom,
                Image = image
            };

            form.Controls.Add(pictureBox);
            form.Show();
        }

        private static Image ImageFromRawBgraArray(byte[] pixelData, int width, int height)
        {
            // Create a Bitmap object from raw BGRA pixel data
            var bitmap = new Bitmap(width, height, System.Drawing.Imaging.PixelFormat.Format32bppArgb);
            var rect = new Rectangle(0, 0, width, height);

            var bitmapData = bitmap.LockBits(rect, System.Drawing.Imaging.ImageLockMode.WriteOnly, bitmap.PixelFormat);
            System.Runtime.InteropServices.Marshal.Copy(pixelData, 0, bitmapData.Scan0, pixelData.Length);
            bitmap.UnlockBits(bitmapData);

            return bitmap;
        }
    }
}

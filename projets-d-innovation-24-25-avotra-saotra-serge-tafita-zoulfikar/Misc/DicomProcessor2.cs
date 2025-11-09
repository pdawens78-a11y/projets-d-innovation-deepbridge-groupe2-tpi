using System;
using System.Collections.Generic;
using System.Drawing.Imaging;
using System.Drawing;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using EvilDICOM.Core.Element;
using EvilDICOM.Core.Helpers;
using EvilDICOM.Core;
using System.Windows.Forms;
using System.Runtime.InteropServices;

namespace DeepBridgeWindowsApp
{
    internal class DicomProcessor2
    {
        private readonly string dicomPath = @"C:\Users\Duck\Documents\Cours\M2 MBDS\Deep Bridge\dataset_chu_nice_2020_2021\1.2.840.113619.2.5.77241951.30716.1506527979.913.dcm";

        public void Run()
        {
            try
            {
                Console.WriteLine($"Loading DICOM from: {dicomPath}");
                var dicomFile = DICOMObject.Read(dicomPath);
                ProcessAndDisplayDicom(dicomFile);
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Error: {ex.Message}");
            }
        }

        private void ProcessAndDisplayDicom(DICOMObject dicomFile)
        {
            // Extract metadata
            var rows = Convert.ToInt32(dicomFile.FindFirst(TagHelper.Rows)?.DData ?? 0);
            var columns = Convert.ToInt32(dicomFile.FindFirst(TagHelper.Columns)?.DData ?? 0);
            var windowCenter = Convert.ToDouble(dicomFile.FindFirst(TagHelper.WindowCenter)?.DData ?? 40.0);
            var windowWidth = Convert.ToDouble(dicomFile.FindFirst(TagHelper.WindowWidth)?.DData ?? 400.0);

            // Retrieve pixel data
            var pixelData = dicomFile.FindFirst(TagHelper.PixelData)?.DData_;
            if (pixelData == null)
            {
                MessageBox.Show("Pixel data not found in DICOM file.");
                return;
            }

            // Convert pixel data to byte array
            var pixelDataArray = pixelData.Cast<byte>().ToArray();
            if (pixelDataArray.Length == 0)
            {
                MessageBox.Show("Pixel data is empty or invalid.");
                return;
            }

            // Process pixel data
            var bitmap = CreateBitmapFromPixelData(pixelDataArray, rows, columns, windowCenter, windowWidth);

            if (bitmap == null)
            {
                MessageBox.Show("Unable to create bitmap from pixel data.");
                return;
            }

            Form form = new Form
            {
                Text = "DICOM Viewer",
                Size = new Size(600, 600)
            };

            // Display in PictureBox
            PictureBox pictureBox = new PictureBox
            {
                Image = bitmap,
                Dock = DockStyle.Fill,
                SizeMode = PictureBoxSizeMode.Zoom
            };
            form.Controls.Add(pictureBox);
            form.Show();
            Application.Run(form);
        }

        private Bitmap CreateBitmapFromPixelData(byte[] pixelData, int rows, int columns, double windowCenter, double windowWidth)
        {
            Bitmap bitmap = new Bitmap(columns, rows, PixelFormat.Format8bppIndexed);

            // Set grayscale palette
            var palette = bitmap.Palette;
            for (int i = 0; i < 256; i++)
            {
                palette.Entries[i] = Color.FromArgb(i, i, i);
            }
            bitmap.Palette = palette;

            var minPixelValue = windowCenter - 0.5 - (windowWidth - 1) / 2.0;
            var maxPixelValue = windowCenter - 0.5 + (windowWidth - 1) / 2.0;

            BitmapData bmpData = bitmap.LockBits(new Rectangle(0, 0, bitmap.Width, bitmap.Height),
                                                 ImageLockMode.WriteOnly,
                                                 PixelFormat.Format8bppIndexed);

            IntPtr ptr = bmpData.Scan0;
            int stride = bmpData.Stride;
            byte[] grayscaleData = new byte[stride * rows];

            for (int row = 0; row < rows; row++)
            {
                for (int col = 0; col < columns; col++)
                {
                    int pixelIndex = row * columns + col;
                    int bitmapIndex = row * stride + col;

                    if (pixelIndex < pixelData.Length)
                    {
                        double scaledValue = 255.0 * (pixelData[pixelIndex] - minPixelValue) / (maxPixelValue - minPixelValue);
                        grayscaleData[bitmapIndex] = (byte)Clamp(scaledValue, 0, 255);
                    }
                }
            }

            System.Runtime.InteropServices.Marshal.Copy(grayscaleData, 0, ptr, grayscaleData.Length);
            bitmap.UnlockBits(bmpData);

            return bitmap;
        }

        private int Clamp(double value, int min, int max)
        {
            return (int)(value < min ? min : (value > max ? max : value));
        }
    }
}

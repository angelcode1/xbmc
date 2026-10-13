/*
 *  Copyright (C) 2005-2018 Team Kodi
 *  This file is part of Kodi - https://kodi.tv
 *
 *  SPDX-License-Identifier: GPL-2.0-or-later
 *  See LICENSES/README.md for more information.
 */

#include "MediaSource.h"
#include "filesystem/File.h"
#include "settings/MediaSourceSettings.h"
#include "test/TestUtils.h"
#include "utils/XBMCTinyXML2.h"
#include "utils/XMLUtils.h"

#include <gtest/gtest.h>

namespace
{
class TestMediaSourceSettingsDevicePath : public testing::Test, protected CMediaSourceSettings
{
};
} // namespace

TEST_F(TestMediaSourceSettingsDevicePath, UpdateSourcePath)
{
  CMediaSource source;
  source.FromNameAndPaths("Disc", {"D:\\"});
  auto* sources = GetSources("video");
  sources->push_back(source);

  ASSERT_TRUE(UpdateSource("video", "Disc", "path", "E:\\"));
#ifdef TARGET_WINDOWS
  EXPECT_EQ(sources->front().strDevicePath, "E:");
#else
  EXPECT_TRUE(sources->front().strDevicePath.empty());
#endif

  ASSERT_TRUE(UpdateSource("video", "Disc", "path", "smb://server/share/"));
  EXPECT_TRUE(sources->front().strDevicePath.empty());
  EXPECT_EQ(sources->front().m_iDriveType, SourceType::REMOTE);
}

TEST_F(TestMediaSourceSettingsDevicePath, ReloadDriveSource)
{
  CMediaSource source;
  source.FromNameAndPaths("Disc", {"E:\\"});
  GetSources("video")->push_back(source);

  XFILE::CFile* file = XBMC_CREATETEMPFILE(".xml");
  ASSERT_NE(file, nullptr);
  const std::string xmlfile = XBMC_TEMPFILEPATH(file);
  file->Close();

  EXPECT_TRUE(Save(xmlfile));
  Clear();
  EXPECT_TRUE(Load(xmlfile));
  EXPECT_TRUE(XBMC_DELETETEMPFILE(file));

  const auto* sources = GetSources("video");
  ASSERT_EQ(sources->size(), 1);
#ifdef TARGET_WINDOWS
  EXPECT_EQ(sources->front().strDevicePath, "E:");
#else
  EXPECT_TRUE(sources->front().strDevicePath.empty());
#endif
}

TEST_F(TestMediaSourceSettingsDevicePath, GazelleVirtualOpticalUdfSource)
{
  // A real Gazelle UDF VFS URL is not the legacy D:\\ optical-drive path.
  constexpr const char* disc = "udf://gazelleoptical%3A%2F%2Fdrive0%2Fimage/";
  CMediaSource share;
  share.FromNameAndPaths("Physical Blu-ray Drive", {disc});
  EXPECT_EQ(share.strPath, disc);
  ASSERT_EQ(share.vecPaths.size(), 1);
  EXPECT_EQ(share.vecPaths.front(), disc);
  EXPECT_EQ(share.m_iDriveType, SourceType::VIRTUAL_OPTICAL_DISC);

  // All other UDF inputs retain Kodi's historical mapping.
  CMediaSource legacy;
  legacy.FromNameAndPaths("Other UDF", {"udf://other%3A%2F%2Fimage/"});
  EXPECT_EQ(legacy.strPath, "D:\\\\");
}

TEST_F(TestMediaSourceSettingsDevicePath, GazelleSourceSaveReload)
{
  constexpr const char* disc = "udf://gazelleoptical%3A%2F%2Fdrive0%2Fimage/";
  CMediaSource source;
  source.FromNameAndPaths("Physical Blu-ray Drive", {disc});
  source.m_allowSharing = false;
  GetSources("video")->push_back(source);

  XFILE::CFile* file = XBMC_CREATETEMPFILE(".xml");
  ASSERT_NE(file, nullptr);
  const std::string xmlFile = XBMC_TEMPFILEPATH(file);
  file->Close();

  ASSERT_TRUE(Save(xmlFile));
  Clear();
  ASSERT_TRUE(Load(xmlFile));
  ASSERT_TRUE(XBMC_DELETETEMPFILE(file));

  const auto* videoSources = GetSources("video");
  ASSERT_EQ(videoSources->size(), 1);
  EXPECT_EQ(videoSources->front().strName, "Physical Blu-ray Drive");
  EXPECT_EQ(videoSources->front().strPath, disc);
  ASSERT_EQ(videoSources->front().vecPaths.size(), 1);
  EXPECT_EQ(videoSources->front().vecPaths.front(), disc);
  EXPECT_FALSE(videoSources->front().m_allowSharing);
}

TEST(TestMediaSourceSettings, LoadString)
{
  CMediaSourceSettings& ms = CMediaSourceSettings::GetInstance();
  EXPECT_TRUE(ms.Load(XBMC_REF_FILE_PATH("/xbmc/settings/test/test-MediaSources.xml")));

  EXPECT_EQ(ms.GetSources("programs")->size(), 0);
  EXPECT_EQ(ms.GetSources("files")->size(), 0);
  EXPECT_EQ(ms.GetSources("music")->size(), 2);
  EXPECT_EQ(ms.GetSources("video")->size(), 4);
  EXPECT_EQ(ms.GetSources("pictures")->size(), 1);
  EXPECT_EQ(ms.GetSources("games")->size(), 0);
}

TEST(TestMediaSourceSettings, SaveString)
{
  CMediaSourceSettings& ms = CMediaSourceSettings::GetInstance();
  EXPECT_TRUE(ms.Load(XBMC_REF_FILE_PATH("/xbmc/settings/test/test-MediaSources.xml")));

  int refprograms = ms.GetSources("programs")->size();
  int reffiles = ms.GetSources("files")->size();
  int refmusic = ms.GetSources("music")->size();
  int refvideo = ms.GetSources("video")->size();
  int refpictures = ms.GetSources("pictures")->size();
  int refgames = ms.GetSources("games")->size();

  XFILE::CFile* file;
  file = XBMC_CREATETEMPFILE(".xml");
  std::string xmlfile = XBMC_TEMPFILEPATH(file);
  file->Close();

  EXPECT_TRUE(ms.Save(xmlfile));
  ms.Clear();
  EXPECT_TRUE(ms.Load(xmlfile));
  auto progsources = ms.GetSources("programs");
  auto progsources2 = ms.GetSources("myprograms");
  EXPECT_TRUE(progsources == progsources2);
  EXPECT_EQ(progsources->size(), refprograms);
  auto filessources = ms.GetSources("files");
  EXPECT_EQ(filessources->size(), reffiles);
  auto musicsources = ms.GetSources("music");
  EXPECT_EQ(musicsources->size(), refmusic);
  auto videosources = ms.GetSources("video");
  auto videosources2 = ms.GetSources("videos");
  EXPECT_TRUE(videosources == videosources2);
  EXPECT_EQ(videosources->size(), refvideo);
  auto picturessources = ms.GetSources("pictures");
  EXPECT_EQ(picturessources->size(), refpictures);
  auto gamessources = ms.GetSources("games");
  EXPECT_EQ(gamessources->size(), refgames);

  EXPECT_TRUE(XBMC_DELETETEMPFILE(file));
}

TEST(TestMediaSourceSettings, GetSource)
{
  // ToDo: implement test
  //  Test Malformed source
  //  Test missing name/path element
}

TEST(TestMediaSourceSettings, SetSources)
{
  // ToDo: implement test
}
